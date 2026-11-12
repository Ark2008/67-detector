from app.services.vision.base import (
    GESTURE_NONE,
    GESTURE_SIX_SEVEN,
    DetectGesture,
    FrameDict,
    GestureResult,
)
from app.services.vision.stub import detect_gesture as stub_detect_gesture

# Единственное место, где выбирается реализация CV.
# TODO: когда модуль в cv/gesture_detector будет готов, импортировать его detect_gesture сюда
# вместо заглушки — сигнатура та же, остальной код менять не нужно.
default_detect_gesture: DetectGesture = stub_detect_gesture

__all__ = [
    "GESTURE_NONE",
    "GESTURE_SIX_SEVEN",
    "DetectGesture",
    "FrameDict",
    "GestureResult",
    "default_detect_gesture",
    "stub_detect_gesture",
]
