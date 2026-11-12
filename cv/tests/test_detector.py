import math

import pytest

from cv.gesture_detector import DetectorConfig, Gesture67Detector


def hand(x, y):
    """MediaPipe-shaped input: 21 points with a shared translation."""
    return [
        {"x": x + (i % 5 - 2) * 0.006, "y": y + (i // 5 - 2) * 0.004, "z": 0.0}
        for i in range(21)
    ]


def frames(detector, left_y, right_y, *, fps=30, duration_s=2.5, swap=False,
           start=0.0, collect=False):
    results = []
    for i in range(int(duration_s * fps)):
        t = start + i / fps
        hands = [hand(.25, left_y(t - start)), hand(.75, right_y(t - start))]
        if swap and i % 2:
            hands.reverse()
        result = detector.update(hands, t)
        results.append(result)
    return results if collect else any(r.detected for r in results)


def wave(t):
    return 0.075 * math.sin(2 * math.pi * 1.35 * t)


def test_detects_67():
    detector = Gesture67Detector()
    results = frames(detector, lambda t: .5 + wave(t), lambda t: .5 - wave(t), collect=True)
    assert any(r.detected for r in results)
    assert all(r.correlation is None or -1 <= r.correlation <= 1 for r in results)


def test_media_pipe_list_order_does_not_matter():
    assert frames(Gesture67Detector(), lambda t: .5 + wave(t),
                  lambda t: .5 - wave(t), swap=True)


def test_stationary_hands_not_detected():
    assert not frames(Gesture67Detector(), lambda t: .5, lambda t: .5)


def test_both_hands_move_same_direction():
    assert not frames(Gesture67Detector(), lambda t: .5 + wave(t),
                      lambda t: .55 + wave(t))


def test_one_hand_moves_other_stationary():
    assert not frames(Gesture67Detector(), lambda t: .5 + wave(t),
                      lambda t: .5)


def test_small_jitter_ignored():
    assert not frames(Gesture67Detector(),
                      lambda t: .5 + 0.007 * math.sin(32 * t),
                      lambda t: .5 - 0.007 * math.sin(32 * t))


def test_works_with_15_fps():
    assert frames(Gesture67Detector(), lambda t: .5 + wave(t),
                  lambda t: .5 - wave(t), fps=15)


def test_two_hands_required():
    detector = Gesture67Detector()
    for i in range(40):
        assert not detector.update([hand(.25, .4)], i / 30).detected


def test_gap_clears_partial_history():
    d = Gesture67Detector()
    for i in range(10):
        t = i / 30
        d.update([hand(.25, .5 + wave(t)), hand(.75, .5 - wave(t))], t)
    result = d.update([hand(.25, .5), hand(.75, .5)], 10.0)
    assert result.reason == "collecting_frames"


def test_recognition_has_no_scoring_cooldown():
    results = frames(Gesture67Detector(), lambda t: .5 + wave(t),
                     lambda t: .5 - wave(t), collect=True)
    assert any(a.detected and b.detected for a, b in zip(results, results[1:]))
    assert all(r.reason != "cooldown" for r in results)


def test_invalid_timestamp():
    d = Gesture67Detector()
    d.update([], 1.0)
    with pytest.raises(ValueError, match="increase strictly"):
        d.update([], 1.0)


def test_invalid_landmarks():
    d = Gesture67Detector()
    with pytest.raises(ValueError, match="21"):
        d.update([[{"x": .1, "y": .2}], hand(.7, .5)], 0.0)


def test_close_hands_ignored():
    d = Gesture67Detector()
    assert d.update([hand(.48, .5), hand(.51, .5)], 0.0).reason == "hands_too_close"


def test_reset_allows_new_time_sequence():
    d = Gesture67Detector()
    d.update([], 100.0)
    d.reset()
    assert d.update([], 0.0).reason == "need_two_hands"

# Additional tests for lost tracking and palm geometry.

def world_hand(label="Right", pose="up", curled=False):
    """Synthetic WORLD landmarks for a hand with four extended fingers."""
    side = 1 if label == "Right" else -1
    if pose == "up":
        forward = (0.0, 0.0, 1.0)
    elif pose == "down":
        forward = (0.0, 0.0, -1.0)
    elif pose == "front":
        forward = (0.0, -1.0, 0.0)
    else:
        raise ValueError(pose)

    def step(point, amount, vector):
        return tuple(a + amount * b for a, b in zip(point, vector))

    output = [(0.0, 0.0, 0.0)] * 21
    width_positions = [-.055, -.018, .018, .055]
    for finger, (mcp, pip, dip, tip) in enumerate(((5, 6, 7, 8), (9, 10, 11, 12),
                                                    (13, 14, 15, 16), (17, 18, 19, 20))):
        p = (width_positions[finger] * side, 0.0, 0.0)
        p = step(p, .08, forward)
        output[mcp] = p
        output[pip] = step(p, .035, forward)
        if curled:
            width = (side, 0, 0)
            output[dip] = step(output[pip], .03, width)
            output[tip] = step(output[dip], -.035, forward)
        else:
            output[dip] = step(output[pip], .03, forward)
            output[tip] = step(output[dip], .027, forward)
    output[0] = (0., 0., 0.)
    return output


def strict_frames(detector, left_pose="up", right_pose="up", curled=False, fps=30):
    results = []
    for i in range(90):
        t = i / fps
        results.append(detector.update(
            [hand(.25, .5 + wave(t)), hand(.75, .5 - wave(t))], t,
            world_hands=[world_hand("Left", left_pose, curled),
                         world_hand("Right", right_pose, curled)],
            handedness=["Left", "Right"],
        ))
    return results


def test_short_hand_loss_keeps_motion_and_still_detects():
    detector = Gesture67Detector(DetectorConfig(max_gap_s=.45))
    results = []
    for i in range(90):
        t = i / 30
        hands = ([hand(.25, .5 + wave(t)), hand(.75, .5 - wave(t))]
                 if not (19 <= i <= 26) else [hand(.25, .5 + wave(t))])
        results.append(detector.update(hands, t))
    assert any(r.reason == "temporary_hand_loss" for r in results)
    assert any(r.detected for r in results)


def test_long_loss_clears_partial_motion():
    detector = Gesture67Detector(DetectorConfig(max_gap_s=.35))
    for i in range(12):
        t = i / 30
        detector.update([hand(.25, .5 + wave(t)), hand(.75, .5 - wave(t))], t)
    for i in range(12, 32):
        result = detector.update([], i / 30)
    assert result.reason == "need_two_hands"
    result = detector.update([hand(.25, .5), hand(.75, .5)], 32 / 30)
    assert result.reason == "collecting_frames"


def test_no_ghost_detection_during_missing_frames():
    detector = Gesture67Detector()
    for i in range(5):
        detector.update([hand(.25, .5), hand(.75, .5)], i / 30)
    for i in range(5, 12):
        result = detector.update([], i / 30)
        assert not result.detected
        assert result.reason == "temporary_hand_loss"


def test_upward_open_palms_detected_in_strict_mode():
    results = strict_frames(Gesture67Detector(DetectorConfig(palm_check="up")))
    assert any(r.detected for r in results)
    scores = [r.palm_up_scores for r in results if r.palm_up_scores]
    assert scores and all(s > 0.95 for pair in scores for s in pair)


def test_strict_mode_rejects_palm_facing_camera():
    results = strict_frames(Gesture67Detector(DetectorConfig(palm_check="up")),
                            left_pose="front", right_pose="front")
    assert not any(r.detected for r in results)
    assert any(r.reason == "palms_not_up" for r in results)


def test_strict_mode_rejects_downward_palm():
    results = strict_frames(Gesture67Detector(DetectorConfig(palm_check="up")),
                            left_pose="up", right_pose="down")
    assert not any(r.detected for r in results)
    assert all(not r.detected for r in results)


def test_strict_mode_rejects_bent_fingers():
    results = strict_frames(Gesture67Detector(DetectorConfig(palm_check="up")),
                            curled=True)
    assert not any(r.detected for r in results)
    assert any(r.reason == "fingers_not_open" for r in results)


def test_strict_mode_fails_closed_when_no_world_landmarks():
    detector = Gesture67Detector(DetectorConfig(palm_check="up"))
    assert detector.update([hand(.25, .5), hand(.75, .5)], 0.0).reason == "missing_palm_data"


def test_invert_palm_normal_option():
    detector = Gesture67Detector(DetectorConfig(palm_check="up", palm_normal_sign=-1))
    results = strict_frames(detector, left_pose="down", right_pose="down")
    assert any(r.detected for r in results)


def test_order_swaps_with_world_landmarks():
    detector = Gesture67Detector(DetectorConfig(palm_check="up"))
    results = []
    for i in range(90):
        t = i / 30
        hands = [hand(.25, .5 + wave(t)), hand(.75, .5 - wave(t))]
        worlds = [world_hand("Left"), world_hand("Right")]
        labels = ["Left", "Right"]
        if i % 2:
            hands.reverse()
            worlds.reverse()
            labels.reverse()
        results.append(detector.update(hands, t, world_hands=worlds, handedness=labels))
    assert any(r.detected for r in results)

# v3: a brief misestimated palm orientation must not destroy the movement.
def test_brief_palm_flicker_retains_alternations():
    detector = Gesture67Detector(DetectorConfig(palm_check="up", max_palm_gap_s=.20))
    results = []
    for i in range(90):
        t = i / 30
        pose = "down" if i in (17, 18, 19, 39, 40, 41, 60, 61) else "up"
        result = detector.update(
            [hand(.25, .5 + wave(t)), hand(.75, .5 - wave(t))], t,
            world_hands=[world_hand("Left", pose), world_hand("Right", pose)],
            handedness=["Left", "Right"],
        )
        results.append(result)
        if pose == "down":
            assert not result.detected  # never score during wrong orientation
    assert any(r.reason == "palm_outlier_ignored" for r in results)
    assert not any(r.reason == "palms_not_up" for r in results)
    assert any(r.detected for r in results)


def test_sustained_wrong_palms_reset_history():
    detector = Gesture67Detector(DetectorConfig(palm_check="up", max_palm_gap_s=.20))
    for i in range(15):
        t = i / 30
        detector.update([hand(.25, .5 + wave(t)), hand(.75, .5 - wave(t))], t,
                        world_hands=[world_hand("Left"), world_hand("Right")],
                        handedness=["Left", "Right"])
    states = []
    for i in range(15, 30):
        t = i / 30
        result = detector.update([hand(.25, .5 + wave(t)), hand(.75, .5 - wave(t))], t,
                                 world_hands=[world_hand("Left", "down"),
                                              world_hand("Right", "down")],
                                 handedness=["Left", "Right"])
        states.append(result.reason)
        assert not result.detected
    assert "temporary_palm_mismatch" in states
    assert "palms_not_up" in states
    t = 1.0
    result = detector.update([hand(.25, .5 + wave(t)), hand(.75, .5 - wave(t))], t,
                             world_hands=[world_hand("Left"), world_hand("Right")],
                             handedness=["Left", "Right"])
    assert result.reason == "collecting_frames"


def test_wrong_palms_before_any_valid_frame_are_rejected():
    detector = Gesture67Detector(DetectorConfig(palm_check="up", max_palm_gap_s=.2))
    result = detector.update([hand(.25, .5), hand(.75, .5)], 0,
                             world_hands=[world_hand("Left", "down"),
                                          world_hand("Right", "down")],
                             handedness=["Left", "Right"])
    assert result.reason == "palms_not_up"


def test_mostly_wrong_orientation_not_admitted_by_brief_good_frames():
    detector = Gesture67Detector(DetectorConfig(
        palm_check="up", max_palm_gap_s=.20, min_valid_palm_fraction=.70))
    states = []
    for i in range(90):
        t = i / 30
        # One good frame out of four; every bad streak stays below .20s.
        pose = "up" if i % 4 == 0 else "down"
        result = detector.update(
            [hand(.25, .5 + wave(t)), hand(.75, .5 - wave(t))], t,
            world_hands=[world_hand("Left", pose), world_hand("Right", pose)],
            handedness=["Left", "Right"],
        )
        states.append(result.reason)
        assert not result.detected
    assert "temporary_palm_mismatch" in states
    assert "palms_not_up" in states  # mostly wrong pose cannot become trusted


def test_negative_palm_grace_raises():
    with pytest.raises(ValueError, match="max_palm_gap_s"):
        DetectorConfig(max_palm_gap_s=-.1)


# v4: wrist rotation can cause many single-frame palm-normal outliers.
def test_repeated_palm_outliers_do_not_interrupt_valid_gesture():
    detector = Gesture67Detector(DetectorConfig(palm_check="up"))
    results = []
    for i in range(120):
        t = i / 30
        # A 2-frame wrong estimate every 6 frames: v3 was frequently paused.
        pose = "down" if i % 6 in (2, 3) else "up"
        result = detector.update(
            [hand(.25, .5 + wave(t)), hand(.75, .5 - wave(t))], t,
            world_hands=[world_hand("Left", pose), world_hand("Right", pose)],
            handedness=["Left", "Right"],
        )
        results.append((pose, result))
    assert any(result.detected for pose, result in results)
    assert not any(result.reason == "palms_not_up" for pose, result in results)
    assert all(not result.detected for pose, result in results if pose == "down")


def test_smoothing_rejects_static_down_pose_even_with_motion():
    results = strict_frames(Gesture67Detector(DetectorConfig(palm_check="up")),
                            left_pose="down", right_pose="down")
    assert not any(r.detected for r in results)


def test_smoothing_does_not_hold_down_orientation_indefinitely():
    detector = Gesture67Detector(DetectorConfig(palm_check="up"))
    states = []
    for i in range(90):
        t = i / 30
        pose = "up" if i < 14 else "down"
        res = detector.update(
            [hand(.25, .5 + wave(t)), hand(.75, .5 - wave(t))], t,
            world_hands=[world_hand("Left", pose), world_hand("Right", pose)],
            handedness=["Left", "Right"],
        )
        states.append(res.reason)
        if pose == "down":
            assert not res.detected
    assert "palms_not_up" in states


def test_palm_hysteresis_bounds():
    with pytest.raises(ValueError, match="palm_hold_score"):
        DetectorConfig(palm_hold_score=0.7)
    with pytest.raises(ValueError, match="palm_smoothing_s"):
        DetectorConfig(palm_smoothing_s=-1)


def test_brief_finger_tracking_errors_preserve_valid_movement():
    detector = Gesture67Detector(DetectorConfig(palm_check="up"))
    results = []
    for i in range(120):
        t = i / 30
        curled = i % 9 in (3, 4)
        result = detector.update(
            [hand(.25, .5 + wave(t)), hand(.75, .5 - wave(t))], t,
            world_hands=[world_hand("Left", curled=curled),
                         world_hand("Right", curled=curled)],
            handedness=["Left", "Right"],
        )
        results.append((curled, result))
    assert any(r.detected for _, r in results)
    assert all(not r.detected for curled, r in results if curled)
    assert any(r.reason == "finger_outlier_ignored" for curled, r in results if curled)
