"""Recognition from external coordinates; no camera or scoring dependencies."""

from .detector import DetectionResult, DetectorConfig, Gesture67Detector
from .api import detect_gesture

__all__ = ["DetectionResult", "DetectorConfig", "Gesture67Detector", "detect_gesture"]
