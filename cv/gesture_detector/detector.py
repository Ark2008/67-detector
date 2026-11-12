"""Time-based two-hand 6–7 detector (no third-party dependencies).

Input: 21 normalized MediaPipe hand landmarks per detected hand and timestamp.
Optional strict palm check: corresponding 3D ``hand_world_landmarks`` and
MediaPipe ``handedness`` labels ("Left" / "Right").

This detector cannot recover a genuinely invisible hand. It retains recent
movement state through a short occlusion but never invents observations.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import isfinite, sqrt
from statistics import median
from typing import Any, Sequence


PALM_INDICES = (0, 5, 9, 13, 17)
FINGER_CHAINS = ((5, 6, 7, 8), (9, 10, 11, 12),
                 (13, 14, 15, 16), (17, 18, 19, 20))


@dataclass(frozen=True)
class DetectorConfig:
    window_s: float = 2.0
    min_observation_s: float = 0.7
    min_samples: int = 12
    min_hand_motion: float = 0.05
    min_relative_motion: float = 0.14
    min_x_separation: float = 0.10
    max_correlation: float = -0.5
    phase_threshold: float = 0.03
    phase_min_frames: int = 2
    min_switches: int = 2
    min_switch_interval_s: float = 0.16
    max_switch_interval_s: float = 1.0
    max_gap_s: float = 0.45  # time allowed WITHOUT 2 hands; history preserved
    max_palm_gap_s: float = 0.20  # tolerate a short unreliable palm orientation
    palm_smoothing_s: float = 0.23  # median over recent palm measurements
    palm_hold_score: float = 0.0  # hysteresis threshold after an accepted up pose
    finger_hold_count: int = 2  # tolerate temporary finger folding/occlusion
    min_valid_palm_fraction: float = 0.70  # avoid counting mostly wrong-palm samples
    palm_check: str = "off"  # off, horizontal (palm plane), up (palm points up)
    min_palm_up_score: float = 0.40  # cosine threshold for upward palm normal
    min_straight_fingers: int = 3  # from the four non-thumb fingers
    min_finger_extension_ratio: float = 0.72
    palm_normal_sign: int = 1  # can be inverted per camera/landmark calibration

    def __post_init__(self) -> None:
        if self.window_s <= 0 or not (0 < self.min_observation_s <= self.window_s):
            raise ValueError("Expected 0 < min_observation_s <= window_s")
        if self.min_samples < 3 or self.phase_min_frames < 1 or self.min_switches < 1:
            raise ValueError("Sample, phase and switch counts must be positive")
        if not -1.0 <= self.max_correlation <= 1.0:
            raise ValueError("max_correlation must be between -1 and 1")
        if self.palm_check not in ("off", "horizontal", "up"):
            raise ValueError("palm_check must be off, horizontal or up")
        if not 0 < self.min_valid_palm_fraction <= 1:
            raise ValueError("min_valid_palm_fraction must be in (0, 1]")
        if not 0 <= self.min_palm_up_score <= 1:
            raise ValueError("min_palm_up_score must be between 0 and 1")
        if not -1 <= self.palm_hold_score <= self.min_palm_up_score:
            raise ValueError("palm_hold_score must be in [-1, min_palm_up_score]")
        if not 0 <= self.finger_hold_count <= self.min_straight_fingers:
            raise ValueError("finger_hold_count must be in [0, min_straight_fingers]")
        if not 0 <= self.min_straight_fingers <= 4:
            raise ValueError("min_straight_fingers must be from 0 to 4")
        if not 0 <= self.min_finger_extension_ratio <= 1:
            raise ValueError("min_finger_extension_ratio must be between 0 and 1")
        if self.palm_normal_sign not in (-1, 1):
            raise ValueError("palm_normal_sign must be -1 or 1")
        for key in (
            "min_hand_motion", "min_relative_motion", "min_x_separation",
            "phase_threshold", "min_switch_interval_s", "max_switch_interval_s",
            "max_gap_s", "max_palm_gap_s", "palm_smoothing_s",
        ):
            value = getattr(self, key)
            if not isfinite(value) or value < 0:
                raise ValueError(f"{key} must be nonnegative and finite")
        if self.max_switch_interval_s < self.min_switch_interval_s:
            raise ValueError("max_switch_interval_s must be >= min_switch_interval_s")


@dataclass(frozen=True)
class DetectionResult:
    detected: bool
    reason: str
    switches: int = 0
    relative_motion: float = 0.0
    correlation: float | None = None
    palm_up_scores: tuple[float, float] | None = None
    straight_fingers: tuple[int, int] | None = None
    smoothed_palm_scores: tuple[float, float] | None = None


@dataclass(frozen=True)
class _Frame:
    time_s: float
    left_y: float  # left side in the camera image
    right_y: float
    verified_palm: bool = True  # False while waiting for a recovered palm orientation


def _xy(point: Any) -> tuple[float, float]:
    if isinstance(point, dict):
        x, y = point["x"], point["y"]
    elif hasattr(point, "x") and hasattr(point, "y"):
        x, y = point.x, point.y
    else:
        x, y = point[0], point[1]
    x, y = float(x), float(y)
    if not (isfinite(x) and isfinite(y)):
        raise ValueError("Landmark coordinates must be finite")
    return x, y


def _xyz(point: Any) -> tuple[float, float, float]:
    if isinstance(point, dict):
        xyz = (point["x"], point["y"], point["z"])
    elif hasattr(point, "x") and hasattr(point, "z"):
        xyz = (point.x, point.y, point.z)
    else:
        xyz = (point[0], point[1], point[2])
    values = tuple(map(float, xyz))
    if not all(map(isfinite, values)):
        raise ValueError("World landmark coordinates must be finite")
    return values


def _palm_center(hand: Sequence[Any]) -> tuple[float, float]:
    if len(hand) != 21:
        raise ValueError("Each hand must contain exactly 21 MediaPipe landmarks")
    points = [_xy(hand[i]) for i in PALM_INDICES]
    return (sum(x for x, _ in points) / len(points),
            sum(y for _, y in points) / len(points))


def _subtract(a: tuple[float, float, float], b: tuple[float, float, float]):
    return tuple(x - y for x, y in zip(a, b))


def _norm(a: tuple[float, float, float]) -> float:
    return sqrt(sum(x * x for x in a))


def _palm_geometry(world_hand: Sequence[Any], label: str, normal_sign: int):
    """Return (signed up-facing normal cosine, number of extended fingers).

    The normal is based on wrist/index/pinky MCPs, then oriented consistently
    using MediaPipe handedness. Y increases DOWN in camera coordinates.
    If the camera is oriented/mirrored differently, invert ``normal_sign``.
    """
    if len(world_hand) != 21:
        raise ValueError("World hand must contain exactly 21 landmarks")
    if label not in ("Left", "Right"):
        raise ValueError("Handedness must be Left or Right")

    xyz = [_xyz(p) for p in world_hand]
    across = _subtract(xyz[17], xyz[5])
    forward = _subtract(xyz[9], xyz[0])
    normal_y = across[2] * forward[0] - across[0] * forward[2]
    normal_x = across[1] * forward[2] - across[2] * forward[1]
    normal_z = across[0] * forward[1] - across[1] * forward[0]
    normal_length = _norm((normal_x, normal_y, normal_z))
    if normal_length < 1e-9:
        upness = 0.0
    else:
        handedness_sign = 1 if label == "Right" else -1
        upness = -normal_y / normal_length * handedness_sign * normal_sign

    return upness, xyz


def _straight_finger_count(xyz: Sequence[tuple[float, float, float]],
                           min_ratio: float) -> int:
    count = 0
    for mcp, pip, dip, tip in FINGER_CHAINS:
        length = (_norm(_subtract(xyz[pip], xyz[mcp]))
                  + _norm(_subtract(xyz[dip], xyz[pip]))
                  + _norm(_subtract(xyz[tip], xyz[dip])))
        if length > 1e-9 and _norm(_subtract(xyz[tip], xyz[mcp])) / length >= min_ratio:
            count += 1
    return count


def _correlation(xs: list[float], ys: list[float]) -> float | None:
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    xx = sum(x * x for x in dx)
    yy = sum(y * y for y in dy)
    if xx < 1e-12 or yy < 1e-12:
        return None
    return max(-1.0, min(1.0, sum(x * y for x, y in zip(dx, dy)) / sqrt(xx * yy)))


def _count_switches(samples: list[_Frame], threshold: float, min_frames: int,
                    min_interval: float, max_interval: float) -> int:
    baseline = sum(f.right_y - f.left_y for f in samples) / len(samples)
    accepted_phase = 0
    candidate_phase = 0
    candidate_count = 0
    last_transition_time: float | None = None
    switches = 0
    for frame in samples:
        difference = frame.right_y - frame.left_y - baseline
        phase = 1 if difference >= threshold else -1 if difference <= -threshold else 0
        if phase == 0:
            candidate_phase, candidate_count = 0, 0
            continue
        if phase == candidate_phase:
            candidate_count += 1
        else:
            candidate_phase, candidate_count = phase, 1
        if candidate_count < min_frames or phase == accepted_phase:
            continue
        if accepted_phase != 0:
            assert last_transition_time is not None
            interval = frame.time_s - last_transition_time
            if interval < min_interval:
                continue
            switches = switches + 1 if interval <= max_interval else 0
        accepted_phase = phase
        last_transition_time = frame.time_s
    return switches


class Gesture67Detector:
    """Stateful streaming classifier. Use one instance per video stream.

    A positive result is a classification, not a new scoring event.
    Scoring and cooldown belong exclusively to the backend."""

    def __init__(self, config: DetectorConfig | None = None) -> None:
        self.config = config or DetectorConfig()
        self._samples: deque[_Frame] = deque()
        self._last_timestamp: float | None = None
        self._last_valid_timestamp: float | None = None
        self._palm_mismatch_since: float | None = None
        self._pending_palm_samples: list[_Frame] = []
        self._palm_measurements: deque[tuple[float, tuple[float, float], tuple[int, int]]] = deque()
        self._palms_trusted = False

    def reset(self) -> None:
        self._samples.clear()
        self._last_timestamp = None
        self._last_valid_timestamp = None
        self._palm_mismatch_since = None
        self._pending_palm_samples.clear()
        self._palm_measurements.clear()
        self._palms_trusted = False

    def _discard_motion(self) -> None:
        self._samples.clear()
        self._last_valid_timestamp = None
        self._palm_mismatch_since = None
        self._pending_palm_samples.clear()
        self._palm_measurements.clear()
        self._palms_trusted = False

    def update(self, hands: Sequence[Sequence[Any]], timestamp_s: float, *,
               world_hands: Sequence[Sequence[Any]] | None = None,
               handedness: Sequence[str] | None = None) -> DetectionResult:
        """Append real detections. Missing frames are tolerated, never extrapolated.

        ``world_hands`` and ``handedness`` must be aligned with ``hands``.
        The API is backward-compatible when palm_check='off'.
        """
        timestamp_s = float(timestamp_s)
        if not isfinite(timestamp_s):
            raise ValueError("Timestamp must be finite")
        if self._last_timestamp is not None and timestamp_s <= self._last_timestamp:
            raise ValueError("Timestamps must increase strictly (in seconds)")
        self._last_timestamp = timestamp_s

        if len(hands) != 2:
            # Key change: do not wipe the gesture on 1–N missed frames.
            if (self._last_valid_timestamp is not None and
                    timestamp_s - self._last_valid_timestamp <= self.config.max_gap_s):
                return DetectionResult(False, "temporary_hand_loss")
            self._discard_motion()
            return DetectionResult(False, "need_two_hands")

        centers = [_palm_center(hand) for hand in hands]
        order = sorted(range(2), key=lambda i: centers[i][0])
        (left_x, left_y), (right_x, right_y) = (centers[i] for i in order)
        if right_x - left_x < self.config.min_x_separation:
            self._discard_motion()
            return DetectionResult(False, "hands_too_close")

        palm_scores = None
        finger_counts = None
        smoothed_scores = None
        if self.config.palm_check != "off":
            if (world_hands is None or handedness is None or
                    len(world_hands) != 2 or len(handedness) != 2):
                self._discard_motion()
                return DetectionResult(False, "missing_palm_data")
            geom = [_palm_geometry(world_hands[i], handedness[i],
                                   self.config.palm_normal_sign) for i in order]
            palm_scores = (geom[0][0], geom[1][0])
            finger_counts = tuple(_straight_finger_count(g[1], self.config.min_finger_extension_ratio)
                                  for g in geom)

            # MediaPipe world-landmark normals/handedness can flip for 1-3 frames
            # during a wrist rotation. A rolling median removes isolated outliers.
            self._palm_measurements.append((timestamp_s, palm_scores, finger_counts))
            while (self._palm_measurements and timestamp_s - self._palm_measurements[0][0]
                   > self.config.palm_smoothing_s):
                self._palm_measurements.popleft()
            smoothed_scores = tuple(float(median(obs[1][j] for obs in self._palm_measurements))
                                    for j in range(2))
            smoothed_fingers = tuple(float(median(obs[2][j] for obs in self._palm_measurements))
                                     for j in range(2))

            # Two thresholds prevent oscillation at the acceptance boundary:
            # it takes a strong up score to start a gesture, but a weak/sideways
            # score for a frame or two does not immediately suspend it.
            up_threshold = (self.config.palm_hold_score if self._palms_trusted
                            else self.config.min_palm_up_score)
            finger_threshold = (self.config.finger_hold_count if self._palms_trusted
                                else self.config.min_straight_fingers)
            scores_for_gate = (tuple(map(abs, smoothed_scores))
                               if self.config.palm_check == "horizontal" else smoothed_scores)
            orientation_ok = all(s >= up_threshold for s in scores_for_gate)
            fingers_ok = all(n >= finger_threshold for n in smoothed_fingers)
            if not (orientation_ok and fingers_ok):
                self._palms_trusted = False
                if self._palm_mismatch_since is None:
                    self._palm_mismatch_since = timestamp_s
                # Keep real movement positions provisionally, but don't emit a
                # detection until both palms have recovered to the valid state.
                self._pending_palm_samples.append(
                    _Frame(timestamp_s, left_y, right_y, verified_palm=False)
                )
                details = dict(palm_up_scores=palm_scores, straight_fingers=finger_counts,
                               smoothed_palm_scores=smoothed_scores)
                if (self._last_valid_timestamp is not None and
                        timestamp_s - self._palm_mismatch_since <= self.config.max_palm_gap_s and
                        timestamp_s - self._last_valid_timestamp <= self.config.max_gap_s):
                    reason = "temporary_palm_mismatch" if not orientation_ok else "temporary_finger_mismatch"
                    return DetectionResult(False, reason, **details)
                self._discard_motion()
                return DetectionResult(False, "palms_not_up" if not orientation_ok
                                       else "fingers_not_open", **details)
            self._palms_trusted = True

        if (self._last_valid_timestamp is not None and
                timestamp_s - self._last_valid_timestamp > self.config.max_gap_s):
            self._discard_motion()
        elif self._pending_palm_samples:
            # Accept buffered coordinates only if the orientation recovered
            # within the grace period. No gesture is emitted on invalid frames.
            if (self._palm_mismatch_since is not None and
                    timestamp_s - self._palm_mismatch_since <= self.config.max_palm_gap_s):
                self._samples.extend(self._pending_palm_samples)
            else:
                self._discard_motion()
        self._palm_mismatch_since = None
        self._pending_palm_samples.clear()
        self._last_valid_timestamp = timestamp_s
        self._samples.append(_Frame(timestamp_s, left_y, right_y))
        while self._samples and timestamp_s - self._samples[0].time_s > self.config.window_s:
            self._samples.popleft()
        samples = list(self._samples)
        details = {"palm_up_scores": palm_scores, "straight_fingers": finger_counts,
                   "smoothed_palm_scores": smoothed_scores}
        # The smoothed estimate is trustworthy enough to RETAIN movement, but
        # never award a detection on a frame whose RAW hand normal strongly
        # points down. This is not a reset; the next good frame can complete it.
        if (self.config.palm_check == "up" and palm_scores is not None
                and any(score <= -self.config.min_palm_up_score for score in palm_scores)):
            return DetectionResult(False, "palm_outlier_ignored", **details)
        if (finger_counts is not None and
                any(count < self.config.finger_hold_count for count in finger_counts)):
            return DetectionResult(False, "finger_outlier_ignored", **details)
        if (len(samples) < self.config.min_samples or
                timestamp_s - samples[0].time_s < self.config.min_observation_s):
            return DetectionResult(False, "collecting_frames", **details)

        # A single good frame between mostly downward-facing frames must not
        # turn an entire incorrect gesture into a valid one.
        if (self.config.palm_check != "off" and
                sum(f.verified_palm for f in samples) / len(samples)
                < self.config.min_valid_palm_fraction):
            return DetectionResult(False, "unstable_palm_orientation", **details)

        left = [f.left_y for f in samples]
        right = [f.right_y for f in samples]
        left_range = max(left) - min(left)
        right_range = max(right) - min(right)
        difference = [r - l for l, r in zip(left, right)]
        relative_motion = max(difference) - min(difference)
        if (left_range < self.config.min_hand_motion or
                right_range < self.config.min_hand_motion or
                relative_motion < self.config.min_relative_motion):
            return DetectionResult(False, "insufficient_motion", relative_motion=relative_motion,
                                   **details)

        corr = _correlation(left, right)
        if corr is None or corr > self.config.max_correlation:
            return DetectionResult(False, "not_opposite_motion", relative_motion=relative_motion,
                                   correlation=corr, **details)

        switches = _count_switches(
            samples, self.config.phase_threshold, self.config.phase_min_frames,
            self.config.min_switch_interval_s, self.config.max_switch_interval_s,
        )
        if switches < self.config.min_switches:
            return DetectionResult(False, "waiting_for_alternations", switches,
                                   relative_motion, corr, **details)

        return DetectionResult(True, "gesture_67", switches, relative_motion, corr,
                               **details)
