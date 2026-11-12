from typing import Any

from app.schemas.hands import LANDMARKS_PER_HAND

UP = 0.3
DOWN = 0.7


def make_hand(handedness: str, wrist_y: float) -> dict[str, Any]:
    return {
        "handedness": handedness,
        "score": 0.98,
        "landmarks": [{"x": 0.5, "y": wrist_y, "z": 0.0}] * LANDMARKS_PER_HAND,
    }


def make_frame(
    timestamp_ms: float, *, left_y: float | None = None, right_y: float | None = None
) -> dict[str, Any]:
    """Кадр в формате CV-контракта: без рук, с одной или с двумя."""
    hands = []
    if left_y is not None:
        hands.append(make_hand("Left", left_y))
    if right_y is not None:
        hands.append(make_hand("Right", right_y))
    return {"timestamp_ms": timestamp_ms, "hands": hands}


def swing_frames(count: int, step_ms: float = 300, start_ms: float = 0) -> list[dict[str, Any]]:
    """Кадры «качелей»: выше то левая, то правая рука, начиная с левой. Три кадра — один жест."""
    return [
        make_frame(start_ms + i * step_ms, left_y=UP, right_y=DOWN)
        if i % 2 == 0
        else make_frame(start_ms + i * step_ms, left_y=DOWN, right_y=UP)
        for i in range(count)
    ]


def to_message(frame: dict[str, Any]) -> dict[str, Any]:
    """Сообщение WebSocket `frame` из кадра."""
    return {"type": "frame", **frame}


def swing_messages(count: int, step_ms: float = 300, start_ms: float = 0) -> list[dict[str, Any]]:
    return [to_message(frame) for frame in swing_frames(count, step_ms, start_ms)]
