import pytest

from app.schemas.hands import Handedness
from app.services.vision import SwingGestureDetector, SwingHandTracker


def test_tracker_sees_both_hands() -> None:
    frame = SwingHandTracker().track(b"jpeg", timestamp_ms=100)

    assert frame.timestamp_ms == 100
    assert {hand.handedness for hand in frame.hands} == {Handedness.LEFT, Handedness.RIGHT}


def test_tracker_with_detector_counts_gestures() -> None:
    tracker, detector = SwingHandTracker(swing_frequency_hz=1.5), SwingGestureDetector()

    # 3 секунды кадров по 30 fps; первый взмах уходит на «разгон».
    detected = sum(detector.process(tracker.track(b"jpeg", i * 1000 / 30)) for i in range(90))

    assert detected == 4


def test_empty_image_is_rejected() -> None:
    with pytest.raises(ValueError):
        SwingHandTracker().track(b"", timestamp_ms=0)
