"""Интерфейсы CV-модуля: кадр камеры → координаты рук → засчитан ли жест.

Настоящие реализации из cv/ должны реализовать эти же интерфейсы.
Один экземпляр трекера и детектора живёт одну игровую сессию.
"""

from collections.abc import Callable
from typing import Protocol, TypeAlias

from app.schemas.hands import HandFrame


class HandTracker(Protocol):
    """Поиск рук на кадре камеры (cv/hand_tracking)."""

    def track(self, image: bytes, timestamp_ms: float) -> HandFrame:
        """Найти руки на кадре.

        `image` — закодированное изображение (JPEG/PNG/WebP) как его прислал браузер.
        `timestamp_ms` растёт от кадра к кадру (нужно MediaPipe в режиме VIDEO).
        Если кадр не удалось декодировать — ValueError.
        """
        ...


class GestureDetector(Protocol):
    """Детектор жеста 67 (cv/gesture_detector). Может хранить историю кадров."""

    def process(self, frame: HandFrame) -> bool:
        """Обработать кадр. True — на этом кадре жест засчитан."""
        ...


# Фабрики создают новый трекер и детектор на каждое WebSocket-подключение.
HandTrackerFactory: TypeAlias = Callable[[], HandTracker]
DetectorFactory: TypeAlias = Callable[[], GestureDetector]
