"""Заглушка CV-модуля с согласованной сигнатурой, пока нет настоящего из cv/gesture_detector."""

from itertools import pairwise

from app.services.vision.base import GESTURE_NONE, GESTURE_SIX_SEVEN, FrameDict, GestureResult

WRIST = 0
# Разница высоты запястий меньше этой не считается: руки на одном уровне.
MIN_HEIGHT_DIFF = 0.08
SWINGS_PER_GESTURE = 2
MAX_SWING_INTERVAL_MS = 1000


def detect_gesture(frames: list[FrameDict]) -> GestureResult:
    """Распознать «качели»: руки поочерёдно меняются по высоте.

    Смена «выше левая» ↔ «выше правая» — один взмах. Жест распознан, если в окне есть
    SWINGS_PER_GESTURE взмахов подряд с интервалом не больше MAX_SWING_INTERVAL_MS.
    Сравнивается высота запястий, нужны обе руки.
    """
    # Моменты, когда верхней становилась другая рука.
    changes: list[tuple[float, str]] = []
    for frame in frames:
        upper_hand = _find_upper_hand(frame)
        if upper_hand is not None and (not changes or changes[-1][1] != upper_hand):
            changes.append((frame["timestamp_ms"], upper_hand))

    swings = 0
    for (previous_ms, _), (current_ms, _) in pairwise(changes):
        swings = swings + 1 if current_ms - previous_ms <= MAX_SWING_INTERVAL_MS else 0
        if swings >= SWINGS_PER_GESTURE:
            return {"gesture": GESTURE_SIX_SEVEN}
    return {"gesture": GESTURE_NONE}


def _find_upper_hand(frame: FrameDict) -> str | None:
    wrist_y = {hand["handedness"]: hand["landmarks"][WRIST]["y"] for hand in frame["hands"]}
    if len(wrist_y) != 2:  # нужны обе руки: левая и правая
        return None

    diff = wrist_y["Right"] - wrist_y["Left"]
    if abs(diff) < MIN_HEIGHT_DIFF:
        return None
    # y растёт вниз, поэтому выше та рука, у которой y меньше.
    return "Left" if diff > 0 else "Right"
