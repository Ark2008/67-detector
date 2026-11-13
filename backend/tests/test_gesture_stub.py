from app.services.vision import stub_detect_gesture
from tests.helpers import DOWN, UP, make_frame, swing_frames

SIX_SEVEN = {"gesture": "six_seven"}
NONE = {"gesture": "none"}


def test_two_swings_are_a_gesture() -> None:
    assert stub_detect_gesture(swing_frames(3)) == SIX_SEVEN


def test_one_swing_is_not_a_gesture() -> None:
    assert stub_detect_gesture(swing_frames(2)) == NONE


def test_empty_window_is_not_a_gesture() -> None:
    assert stub_detect_gesture([]) == NONE


def test_frames_without_hands_are_not_a_gesture() -> None:
    assert stub_detect_gesture([make_frame(i * 100) for i in range(10)]) == NONE


def test_same_position_is_not_a_swing() -> None:
    frames = [make_frame(i * 100, left_y=UP, right_y=DOWN) for i in range(10)]

    assert stub_detect_gesture(frames) == NONE


def test_one_hand_is_ignored() -> None:
    frames = [make_frame(i * 300, left_y=UP if i % 2 else DOWN) for i in range(6)]

    assert stub_detect_gesture(frames) == NONE


def test_small_height_difference_is_ignored() -> None:
    frames = [make_frame(i * 300, left_y=0.5, right_y=0.52 if i % 2 else 0.48) for i in range(6)]

    assert stub_detect_gesture(frames) == NONE


def test_slow_swings_are_not_a_gesture() -> None:
    assert stub_detect_gesture(swing_frames(6, step_ms=1500)) == NONE


def test_pause_restarts_swing_counting() -> None:
    # Взмах, долгая пауза и ещё один взмах — это не два взмаха подряд.
    frames = [*swing_frames(2), *swing_frames(2, start_ms=5000)]

    assert stub_detect_gesture(frames) == NONE


def test_gesture_is_found_anywhere_in_window() -> None:
    frames = [*swing_frames(3), *(make_frame(1000 + i * 100) for i in range(10))]

    assert stub_detect_gesture(frames) == SIX_SEVEN
