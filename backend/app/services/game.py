import asyncio
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from app.repositories.game import GameRepository, GestureData
from app.schemas.hands import HandFrame
from app.services.vision import GESTURE_SIX_SEVEN, DetectGesture, FrameDict

Clock = Callable[[], float]


class SessionNotActiveError(Exception):
    """Сессия уже завершена («Стоп» или таймаут): кадры больше не принимаются."""


@dataclass(slots=True)
class SessionGame:
    """Обработка кадров одного WebSocket-подключения: окно кадров → CV → анти-дребезг → БД.

    Правило анти-дребезга живёт здесь, а не в CV (docs/websocket.md). Время считается по
    часам сервера, `timestamp_ms` клиента на cooldown не влияет.
    """

    session_id: uuid.UUID
    repository: GameRepository
    detect_gesture: DetectGesture
    cooldown_ms: int
    window_size: int
    touch_interval_seconds: float
    clock: Clock = time.monotonic

    _frames: deque[FrameDict] = field(init=False)
    _last_gesture_at: float | None = field(default=None, init=False)
    _last_touch_at: float = field(init=False)

    def __post_init__(self) -> None:
        self._frames = deque(maxlen=self.window_size)
        self._last_touch_at = self.clock()

    async def handle_frame(self, frame: HandFrame) -> GestureData | None:
        """Обработать кадр. Вернуть засчитанный жест или None.

        SessionNotActiveError — сессию успели завершить, пока соединение было открыто.
        """
        # В CV уходит кадр в том же виде, что прислал клиент, без служебного поля type.
        self._frames.append(frame.model_dump(mode="json", exclude={"type"}))

        if not self._is_cooling_down() and await self._is_gesture():
            gesture = await self.repository.register_gesture(self.session_id)
            if gesture is None:
                raise SessionNotActiveError
            self._last_gesture_at = self._last_touch_at = self.clock()
            # Кадры засчитанного жеста не должны дать второе срабатывание после cooldown.
            self._frames.clear()
            return gesture

        await self._touch()
        return None

    def _is_cooling_down(self) -> bool:
        if self._last_gesture_at is None:
            return False
        return (self.clock() - self._last_gesture_at) * 1000 < self.cooldown_ms

    async def _is_gesture(self) -> bool:
        # CV может нагружать CPU: считаем в отдельном потоке, чтобы не блокировать event loop.
        result = await asyncio.to_thread(self.detect_gesture, list(self._frames))
        return result["gesture"] == GESTURE_SIX_SEVEN

    async def _touch(self) -> None:
        """Обновить last_activity_at, но не чаще раза в touch_interval_seconds."""
        now = self.clock()
        if now - self._last_touch_at < self.touch_interval_seconds:
            return
        if not await self.repository.touch_session(self.session_id):
            raise SessionNotActiveError
        self._last_touch_at = now
