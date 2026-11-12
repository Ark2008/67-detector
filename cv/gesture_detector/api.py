"""Adapter for the frame schema in docs/websocket.md."""

from collections.abc import Mapping
from math import isfinite

from .detector import DetectorConfig, Gesture67Detector


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return value


def _points(points, *, world=False):
    if not isinstance(points, (list, tuple)) or len(points) != 21:
        raise ValueError("landmarks length != 21")
    for point in points:
        if not isinstance(point, Mapping):
            raise ValueError("each landmark must be an object with x, y, z")
        for axis in ("x", "y", "z"):
            value = _number(point.get(axis), axis)
            if not world and axis != "z" and not 0 <= value <= 1:
                raise ValueError("normalized x and y must be in [0, 1]")


def detect_gesture(frames, *, config: DetectorConfig | None = None) -> dict[str, str]:
    """Classify the final frame's window, independently on every call.

    Input is a list/tuple of chronological WS frame dictionaries. Milliseconds
    are converted to seconds. No per-session state is retained. An optional
    world_landmarks field enables palm_check='up' or 'horizontal'; absent world
    coordinates never silently disable a requested palm check.
    Malformed input raises ValueError, suitable for backend invalid_payload.
    """
    if not isinstance(frames, (list, tuple)):
        raise ValueError("frames must be a list or tuple")
    detector = Gesture67Detector(config)
    detected = False
    for frame in frames:
        if not isinstance(frame, Mapping):
            raise ValueError("each frame must be an object")
        timestamp = _number(frame.get("timestamp_ms"), "timestamp_ms") / 1000
        hands = frame.get("hands")
        if not isinstance(hands, (list, tuple)) or len(hands) > 2:
            raise ValueError("hands must contain 0, 1 or 2 hands")
        landmarks, worlds, labels = [], [], []
        reliable = True
        for hand in hands:
            if not isinstance(hand, Mapping):
                raise ValueError("each hand must be an object")
            label = hand.get("handedness")
            if label not in ("Left", "Right") or label in labels:
                raise ValueError("handedness must be unique Left/Right labels")
            labels.append(label)
            score = _number(hand.get("score"), "score")
            if not 0 <= score <= 1:
                raise ValueError("score must be in [0, 1]")
            reliable = reliable and score >= 0.5
            _points(hand.get("landmarks"))
            landmarks.append(hand["landmarks"])
            if hand.get("world_landmarks") is not None:
                _points(hand["world_landmarks"], world=True)
                worlds.append(hand["world_landmarks"])
        result = detector.update(
            landmarks if reliable else [], timestamp,
            world_hands=worlds if len(worlds) == len(hands) else None,
            handedness=labels,
        )
        detected = result.detected
    return {"gesture": "six_seven" if detected else "none"}
