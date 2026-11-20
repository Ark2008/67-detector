from cv.gesture_detector import detect_gesture

from app.services.vision.base import (
    GESTURE_NONE,
    GESTURE_SIX_SEVEN,
    DetectGesture,
    FrameDict,
    GestureResult,
)
from app.services.vision.stub import detect_gesture as stub_detect_gesture

default_detect_gesture: DetectGesture = detect_gesture

__all__ = [
    "GESTURE_NONE",
    "GESTURE_SIX_SEVEN",
    "DetectGesture",
    "FrameDict",
    "GestureResult",
    "default_detect_gesture",
    "stub_detect_gesture",
]
