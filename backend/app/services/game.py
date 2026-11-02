import asyncio
import time
from dataclasses import dataclass, field
from typing import Self

from app.repositories.game_sessions import GameSessionRepository
from app.schemas.hands import HandFrame
from app.services.vision import GestureDetector, HandTracker


@dataclass(slots=True)
class Game:
    """Игровая логика одной сессии: кадр → трекер рук → детектор → счёт в БД."""

    session_id: int
    repository: GameSessionRepository
    tracker: HandTracker
    detector: GestureDetector
    _started_at: float = field(default_factory=time.monotonic, init=False)

    @classmethod
    async def start(
        cls,
        nickname: str,
        repository: GameSessionRepository,
        tracker: HandTracker,
        detector: GestureDetector,
    ) -> Self:
        session_id = await repository.create(nickname)
        return cls(session_id, repository, tracker, detector)

    async def handle_image(self, image: bytes) -> int | None:
        """Обработать кадр камеры. Вернуть новый счёт, если жест засчитан."""
        timestamp_ms = (time.monotonic() - self._started_at) * 1000
        # Поиск рук нагружает CPU: выполняем в отдельном потоке, чтобы не блокировать event loop.
        frame = await asyncio.to_thread(self.tracker.track, image, timestamp_ms)
        return await self.handle_frame(frame)

    async def handle_frame(self, frame: HandFrame) -> int | None:
        """Обработать уже найденные руки. Вернуть новый счёт, если жест засчитан."""
        if not self.detector.process(frame):
            return None
        return await self.repository.increment_score(self.session_id)

    async def finish(self) -> None:
        await self.repository.finish(self.session_id)
