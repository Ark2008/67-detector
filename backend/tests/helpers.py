from typing import Any

from app.schemas.hands import LANDMARKS_PER_HAND, Hand, Handedness, HandFrame, Landmark

UP = 0.3
DOWN = 0.7


def make_hand(handedness: Handedness, wrist_y: float) -> Hand:
    return Hand(handedness=handedness, landmarks=[Landmark(x=0.5, y=wrist_y)] * LANDMARKS_PER_HAND)


def make_frame(
    timestamp_ms: float, *, left_y: float | None = None, right_y: float | None = None
) -> HandFrame:
    hands = []
    if left_y is not None:
        hands.append(make_hand(Handedness.LEFT, left_y))
    if right_y is not None:
        hands.append(make_hand(Handedness.RIGHT, right_y))
    return HandFrame(timestamp_ms=timestamp_ms, hands=hands)


def swing_frames(count: int, step_ms: float = 300) -> list[HandFrame]:
    """Кадры «качелей»: выше то левая, то правая рука, начиная с левой."""
    return [
        make_frame(i * step_ms, left_y=UP, right_y=DOWN)
        if i % 2 == 0
        else make_frame(i * step_ms, left_y=DOWN, right_y=UP)
        for i in range(count)
    ]


def to_message(frame: HandFrame) -> dict[str, Any]:
    return {"type": "hand_landmarks", **frame.model_dump(mode="json")}
