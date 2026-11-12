import copy
import math

import pytest

from cv.gesture_detector import DetectorConfig, detect_gesture
from test_detector import hand, world_hand


def window(fps=20, world=False, pose="up"):
    result = []
    for i in range(fps * 2):
        offset = .075 * math.sin(2 * math.pi * 1.35 * i / fps)
        hands = []
        for x, y, label in ((.25, .5 + offset, "Left"), (.75, .5 - offset, "Right")):
            entry = dict(landmarks=hand(x, y), handedness=label, score=.98)
            if world:
                entry["world_landmarks"] = [dict(zip(("x", "y", "z"), p))
                                             for p in world_hand(label, pose)]
            hands.append(entry)
        result.append(dict(type="frame", timestamp_ms=1730000000000 + i * 1000 / fps,
                           hands=hands))
    return result


@pytest.mark.parametrize("fps", [15, 20, 30])
def test_ws_window(fps):
    assert detect_gesture(window(fps)) == {"gesture": "six_seven"}


def test_stateless_and_does_not_mutate():
    frames = window()
    original = copy.deepcopy(frames)
    assert detect_gesture(frames) == detect_gesture(frames)
    assert frames == original
    assert detect_gesture([]) == {"gesture": "none"}


@pytest.mark.parametrize("hands", [[], [dict(landmarks=hand(.25, .5), handedness="Left", score=.98)]])
def test_no_stale_detection_after_loss(hands):
    frames = window()
    frames.append(dict(timestamp_ms=frames[-1]["timestamp_ms"] + 50, hands=hands))
    assert detect_gesture(frames) == {"gesture": "none"}


def test_gap_resets_history():
    frames = window()
    last = copy.deepcopy(frames[-1])
    last["timestamp_ms"] += 2000
    assert detect_gesture(frames + [last]) == {"gesture": "none"}


def test_strict_world_data():
    config = DetectorConfig(palm_check="up")
    assert detect_gesture(window(world=True), config=config)["gesture"] == "six_seven"
    assert detect_gesture(window(), config=config)["gesture"] == "none"
    assert detect_gesture(window(world=True, pose="down"), config=config)["gesture"] == "none"


@pytest.mark.parametrize("corruption", ["nan", "count", "label", "timestamp", "range", "score"])
def test_invalid_payload(corruption):
    frames = window()
    h = frames[-1]["hands"][0]
    if corruption == "nan":
        h["landmarks"][20]["z"] = float("nan")
    elif corruption == "count":
        h["landmarks"].pop()
    elif corruption == "label":
        h["handedness"] = "Right"
    elif corruption == "timestamp":
        frames[-1]["timestamp_ms"] = frames[-2]["timestamp_ms"]
    elif corruption == "range":
        h["landmarks"][20]["x"] = 2
    else:
        h["score"] = True
    with pytest.raises(ValueError):
        detect_gesture(frames)


def test_low_confidence_is_not_a_gesture():
    frames = window()
    frames[-1]["hands"][0]["score"] = .1
    assert detect_gesture(frames)["gesture"] == "none"
