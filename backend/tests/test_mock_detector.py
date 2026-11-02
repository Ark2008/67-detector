from app.services.vision import SwingGestureDetector
from tests.helpers import DOWN, UP, make_frame, swing_frames


def process_all(detector: SwingGestureDetector, frames) -> list[bool]:
    return [detector.process(frame) for frame in frames]


def test_gesture_is_detected_after_two_swings() -> None:
    assert process_all(SwingGestureDetector(), swing_frames(3)) == [False, False, True]


def test_continuous_swinging_counts_gesture_every_two_swings() -> None:
    results = process_all(SwingGestureDetector(), swing_frames(7))

    assert results == [False, False, True, False, True, False, True]


def test_same_position_does_not_count_as_swing() -> None:
    frames = [make_frame(i * 100, left_y=UP, right_y=DOWN) for i in range(10)]

    assert not any(process_all(SwingGestureDetector(), frames))


def test_one_hand_is_ignored() -> None:
    frames = [make_frame(i * 300, left_y=UP if i % 2 else DOWN) for i in range(6)]

    assert not any(process_all(SwingGestureDetector(), frames))


def test_small_height_difference_is_ignored() -> None:
    frames = [make_frame(i * 300, left_y=0.5, right_y=0.52 if i % 2 else 0.48) for i in range(6)]

    assert not any(process_all(SwingGestureDetector(), frames))


def test_slow_swings_are_not_a_gesture() -> None:
    assert not any(process_all(SwingGestureDetector(), swing_frames(6, step_ms=1500)))


def test_pause_restarts_swing_counting() -> None:
    detector = SwingGestureDetector()
    frames = [
        *swing_frames(2),  # взмах, затем пауза
        make_frame(5000, left_y=UP, right_y=DOWN),  # отсчёт начинается заново
        make_frame(5300, left_y=DOWN, right_y=UP),
        make_frame(5600, left_y=UP, right_y=DOWN),
    ]

    assert process_all(detector, frames) == [False, False, False, False, True]
