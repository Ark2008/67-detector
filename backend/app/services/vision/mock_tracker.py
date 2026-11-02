"""Тестовый трекер рук, пока нет настоящего из cv/."""

import math
from dataclasses import dataclass

from app.schemas.hands import LANDMARKS_PER_HAND, Hand, Handedness, HandFrame, Landmark


@dataclass(slots=True)
class SwingHandTracker:
    """Не смотрит на изображение: всегда «видит» две руки, которые качаются вверх-вниз.

    Вместе с SwingGestureDetector это даёт `swing_frequency_hz` засчитанных жестов
    в секунду на любых кадрах — удобно проверять цепочку без настоящего CV.
    """

    swing_frequency_hz: float = 1.5
    amplitude: float = 0.15

    def track(self, image: bytes, timestamp_ms: float) -> HandFrame:
        if not image:
            raise ValueError("пустой кадр")
        offset = self.amplitude * math.sin(2 * math.pi * self.swing_frequency_hz * timestamp_ms / 1000)
        return HandFrame(
            timestamp_ms=timestamp_ms,
            hands=[make_hand(Handedness.LEFT, 0.5 + offset), make_hand(Handedness.RIGHT, 0.5 - offset)],
        )


def make_hand(handedness: Handedness, wrist_y: float) -> Hand:
    return Hand(handedness=handedness, landmarks=[Landmark(x=0.5, y=wrist_y)] * LANDMARKS_PER_HAND)
