"""Тестовый детектор, пока нет настоящего из cv/."""

from dataclasses import dataclass, field

from app.schemas.hands import Handedness, HandFrame

WRIST = 0


@dataclass(slots=True)
class SwingGestureDetector:
    """Засчитывает жест, когда руки поочерёдно меняются по высоте («качели»).

    Смена «выше левая» ↔ «выше правая» — это один взмах. Жест засчитывается после
    `swings_per_gesture` взмахов подряд, если между ними прошло не больше
    `max_swing_interval_ms`. Сравнивается высота запястий.
    """

    min_height_diff: float = 0.08
    swings_per_gesture: int = 2
    max_swing_interval_ms: float = 1000

    _upper_hand: Handedness | None = field(default=None, init=False)
    _swings: int = field(default=0, init=False)
    _last_swing_ms: float = field(default=0.0, init=False)

    def process(self, frame: HandFrame) -> bool:
        upper_hand = self._find_upper_hand(frame)
        if upper_hand is None or upper_hand == self._upper_hand:
            return False

        is_continuation = (
            self._upper_hand is not None
            and frame.timestamp_ms - self._last_swing_ms <= self.max_swing_interval_ms
        )
        self._swings = self._swings + 1 if is_continuation else 0
        self._upper_hand = upper_hand
        self._last_swing_ms = frame.timestamp_ms

        if self._swings < self.swings_per_gesture:
            return False
        self._swings = 0
        return True

    def _find_upper_hand(self, frame: HandFrame) -> Handedness | None:
        wrist_y = {hand.handedness: hand.landmarks[WRIST].y for hand in frame.hands}
        if len(wrist_y) != 2:  # нужны обе руки: левая и правая
            return None

        diff = wrist_y[Handedness.RIGHT] - wrist_y[Handedness.LEFT]
        if abs(diff) < self.min_height_diff:
            return None
        # y растёт вниз, поэтому выше та рука, у которой y меньше.
        return Handedness.LEFT if diff > 0 else Handedness.RIGHT
