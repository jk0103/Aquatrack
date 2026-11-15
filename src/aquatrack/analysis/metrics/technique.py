"""Technique measures for freestyle filmed underwater from the side.

Everything is measured, nothing is judged (reference ranges come later). Values come only
from points cleanup trusts: confidence of at least `MIN_CONFIDENCE` and not filled in. Each
value carries the confidence of the points it came from and the frame it was read at.

Conventions (in the oriented frame, head to the right):
  - "Horizontal" is the direction of travel (see `aquatrack.analysis.horizon`), so a
    tilted camera doesn't change the angles. "Depth" is measured straight down from it.
  - Lengths are in trunk lengths (shoulder midpoint to hip midpoint), angles in degrees.
  - Arm measures are per trusted stroke cycle (see `cycles`), body and kick measures per
    trusted cycle window, then summarized overall, per arm and per section.
"""

import json
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from aquatrack.analysis.metrics.cycles import StrokeAnalysis, StrokeCycle, main_stretch
from aquatrack.analysis.metrics.signal import find_peaks
from aquatrack.analysis.pose.cleanup import DROPPED, CleanPose, Fix
from aquatrack.analysis.pose.wholebody import (
    LEFT_FOOT,
    LEFT_HAND,
    RIGHT_FOOT,
    RIGHT_HAND,
    WholeBodySequence,
)

MIN_CONFIDENCE = 0.3
CATCH_UPPER_ARM_DEG = 30  # the catch: upper arm this far below the travel line
MIN_KICK_PROMINENCE = 0.05  # trunk lengths; smaller ankle bumps are noise
MIN_KICK_SPACING_S = 0.15
MIN_LEG_COVERAGE = 0.7  # of a cycle's frames with a reliable ankle, to count kicks
PATH_SAMPLES = 20
# Breaths: the nose's depth below the ears drops from its face-down level toward zero.
BREATH_ENTER = 0.4  # a dip starts below this fraction of the face-down level
BREATH_DEEP = 0.3  # and counts as a breath if it reaches this fraction
BREATH_MIN_S = 0.2
BREATH_MIN_CYCLES = 3  # fewer trusted cycles (both arms) is too short to count breaths

ARMS = {"left": (5, 7, 9, LEFT_HAND), "right": (6, 8, 10, RIGHT_HAND)}
# Arm shape measures, which the far arm (behind the body in a side view) gets less right.
ARM_GEOMETRY = (
    "elbow_min_pull",
    "elbow_mean_pull",
    "catch_forearm_from_vertical",
    "catch_elbow_above_wrist",
    "catch_elbow_above_hand",
    "pull_depth",
    "reach_ahead_of_shoulder",
    "entry_ahead_of_shoulder",
    "entry_ahead_of_head",
    "pull_shape_spread",
)
NEAR_SIDE_MIN_GAP = 0.5  # raw RTMW score difference between the arms to call one nearer
FAR_ARM_CONFIDENCE = 0.5
LEGS = {"left": (11, 13, 15, LEFT_FOOT), "right": (12, 14, 16, RIGHT_FOOT)}
NOSE, LEFT_EAR, RIGHT_EAR = 0, 3, 4


@dataclass
class Value:
    """One measurement. Frames are indices into the CleanPose sequence."""

    value: float
    confidence: float
    frame: int | None = None
    side: str | None = None  # "left" or "right" for one arm or leg
    section: str = ""
    cycle_start: int | None = None
    curve: list[float] | None = None


@dataclass
class Measure:
    name: str
    unit: str
    description: str
    values: list[Value] = field(default_factory=list)
    experimental: bool = False
    status: str = ""  # set when the measure can't be taken from this clip
    # Arm measures from a side view: the overall numbers come from the arm nearer the
    # camera when we know which it is; the far arm is often hidden behind the body.
    prefer_side: str | None = None

    def numbers(self, **match) -> np.ndarray:
        return np.array([v.value for v in self._matching(self.values, match)])

    def median(self, **match) -> float:
        values = self.numbers(**match)
        return float(np.median(values)) if len(values) else float("nan")

    @staticmethod
    def _matching(values: list[Value], match: dict) -> list[Value]:
        return [v for v in values if all(getattr(v, k) == x for k, x in match.items())]

    def summary(self) -> dict:
        chosen = self.values
        if self.prefer_side and any(v.side == self.prefer_side for v in self.values):
            chosen = self._matching(self.values, {"side": self.prefer_side})
        values = np.array([v.value for v in chosen])
        out = {
            "unit": self.unit,
            "description": self.description,
            "n": len(values),
        }
        if self.experimental:
            out["experimental"] = True
        if self.status:
            out["status"] = self.status
        if not len(values):
            return out
        if chosen is not self.values:
            out["overall_from"] = f"{self.prefer_side} arm (nearer the camera)"
        out |= {
            "median": _r(np.median(values)),
            "p25": _r(np.percentile(values, 25)),
            "p75": _r(np.percentile(values, 75)),
            "confidence": _r(np.median([v.confidence for v in chosen])),
        }
        sides = {v.side for v in self.values if v.side}
        if sides:
            out["by_side"] = {side: _r(self.median(side=side)) for side in sorted(sides)}
        by_section = {}
        for name in ("start", "middle", "end"):
            section = [v.value for v in self._matching(chosen, {"section": name})]
            if section:
                by_section[name] = float(np.median(section))
        if by_section:
            out["by_section"] = {k: _r(x) for k, x in by_section.items()}
            if "start" in by_section and "end" in by_section:
                out["change_start_to_end"] = _r(by_section["end"] - by_section["start"])
        return out


def _r(x: float) -> float | None:
    return None if x is None or np.isnan(x) else round(float(x), 3)


@dataclass
class TechniqueReport:
    measures: dict[str, Measure]
    horizontal_source: str
    near_side: str | None = None
    balance: dict = field(default_factory=dict)
    session: dict = field(default_factory=dict)

    def to_dict(self, pose: CleanPose) -> dict:
        def frame(i):
            return None if i is None else int(pose.frame_indices[i])

        return {
            "horizontal_reference": self.horizontal_source,
            "near_arm": self.near_side,
            "session": self.session,
            "balance": self.balance,
            "measures": {
                name: m.summary()
                | {
                    "values": [
                        {
                            "value": _r(v.value),
                            "confidence": _r(v.confidence),
                            "frame": frame(v.frame),
                            **({"side": v.side} if v.side else {}),
                            **({"section": v.section} if v.section else {}),
                            **(
                                {"cycle_start_frame": frame(v.cycle_start)}
                                if v.cycle_start is not None
                                else {}
                            ),
                            **({"curve": [_r(x) for x in v.curve]} if v.curve else {}),
                        }
                        for v in m.values
                    ]
                }
                for name, m in self.measures.items()
            },
        }

    def save(self, path: str | Path, pose: CleanPose) -> Path:
        path = Path(path)
        path.write_text(json.dumps(self.to_dict(pose), indent=2))
        return path


def default_measures_path(video_path: str | Path) -> Path:
    video_path = Path(video_path)
    return video_path.with_name(f"{video_path.stem}.measures.json")


def joint_angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Angle at b (degrees) between b->a and b->c, per frame."""
    u, v = a - b, c - b
    cos = np.einsum("fd,fd->f", u, v) / (np.linalg.norm(u, axis=-1) * np.linalg.norm(v, axis=-1))
    return np.degrees(np.arccos(np.clip(cos, -1, 1)))


def angle_between(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Unsigned angle (degrees) between two vectors, per frame."""
    cos = np.einsum("fd,fd->f", u, v) / (np.linalg.norm(u, axis=-1) * np.linalg.norm(v, axis=-1))
    return np.degrees(np.arccos(np.clip(cos, -1, 1)))


class _Geometry:
    """Travel-aligned measurements on a CleanPose."""

    def __init__(self, pose: CleanPose, horizon: np.ndarray):
        self.pose = pose
        self.xy = pose.xy
        self.travel = np.stack([np.cos(horizon), np.sin(horizon)], axis=1)
        self.down = np.stack([-np.sin(horizon), np.cos(horizon)], axis=1)
        self.trunk = pose.trunk

    def along(self, vec: np.ndarray) -> np.ndarray:
        return np.einsum("fd,fd->f", vec, self.travel) / self.trunk

    def depth(self, vec: np.ndarray) -> np.ndarray:
        return np.einsum("fd,fd->f", vec, self.down) / self.trunk

    def tilt(self, vec: np.ndarray) -> np.ndarray:
        """Angle (degrees) of a vector below the travel direction: 0 ahead, 90 down."""
        return np.degrees(np.arctan2(self.depth(vec), self.along(vec)))

    def ok(self, points) -> tuple[np.ndarray, np.ndarray]:
        """Per frame: whether all `points` are trustworthy, and their lowest confidence."""
        points = list(points)
        conf = self.pose.confidence[:, points].min(axis=1)
        flags = np.bitwise_or.reduce(self.pose.flags[:, points], axis=1)
        guessed = (flags & int(Fix.FILLED | DROPPED)) > 0
        finite = np.isfinite(self.xy[:, points]).all(axis=(1, 2)) & np.isfinite(self.trunk)
        return (conf >= MIN_CONFIDENCE) & ~guessed & finite, conf

    def center(self, points, min_fraction: float = 0.5) -> tuple[np.ndarray, np.ndarray]:
        """Median of the trustworthy points of a group (hand, foot), per frame."""
        points = list(points)
        each = np.stack([self.ok([p])[0] for p in points], axis=1)
        xy = np.where(each[..., None], self.xy[:, points], np.nan)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN frames stay NaN
            center = np.nanmedian(xy, axis=1)
        return center, each.mean(axis=1) >= min_fraction


def _pick_median(frames: np.ndarray, values: np.ndarray) -> int:
    """The frame whose value is closest to the median, for key-frame images."""
    return int(frames[np.argmin(np.abs(values - np.median(values)))])


def _arm_measures(g: _Geometry, c: StrokeCycle, out: dict[str, Measure], paths: dict) -> None:
    s, e, w, hand = ARMS[c.arm]
    xy = g.xy
    tag = {"side": c.arm, "section": c.section, "cycle_start": c.start}
    pull = np.arange(c.reach, c.end + 1)
    ok_sew, conf_sew = g.ok([s, e, w])
    ok_sw, conf_sw = g.ok([s, w])
    elbow = joint_angle(xy[:, s], xy[:, e], xy[:, w])
    pf = pull[ok_sew[pull]]

    if len(pf) >= 3:
        k = int(pf[np.argmin(elbow[pf])])
        phase = (pf - c.reach) / max(1, c.end - c.reach)
        curve = np.interp(np.linspace(0, 1, 11), phase, elbow[pf]).tolist()
        out["elbow_min_pull"].values.append(Value(elbow[k], conf_sew[k], k, curve=curve, **tag))
        out["elbow_mean_pull"].values.append(
            Value(
                float(elbow[pf].mean()),
                float(np.median(conf_sew[pf])),
                _pick_median(pf, elbow[pf]),
                **tag,
            )
        )

        upper = g.tilt(xy[:, e] - xy[:, s])
        caught = np.nonzero(upper[pf] >= CATCH_UPPER_ARM_DEG)[0]
        if len(caught):
            k1 = int(pf[caught[0]])
            # Interpolate to the moment the upper arm crosses the mark: between frames the
            # arm turns ~12 degrees at 25 fps, which would shift every catch value.
            k0, t = k1, 1.0
            if caught[0] > 0:
                k0 = int(pf[caught[0] - 1])
                t = (CATCH_UPPER_ARM_DEG - upper[k0]) / (upper[k1] - upper[k0])
            k = k1 if t >= 0.5 else k0
            conf = float(min(conf_sew[k0], conf_sew[k1]))

            def at_catch(series: np.ndarray) -> float:
                return float(series[k0] + t * (series[k1] - series[k0]))

            forearm = angle_between(xy[:, w] - xy[:, e], g.down)
            out["catch_forearm_from_vertical"].values.append(
                Value(at_catch(forearm), conf, k, **tag)
            )
            elbow_above_wrist = g.depth(xy[:, w] - xy[:, e])
            out["catch_elbow_above_wrist"].values.append(
                Value(at_catch(elbow_above_wrist), conf, k, **tag)
            )
            hand_xy, hand_ok = g.center(hand)
            if hand_ok[k0] and hand_ok[k1]:
                above_hand = g.depth(hand_xy - xy[:, e])
                out["catch_elbow_above_hand"].values.append(
                    Value(at_catch(above_hand), conf, k, **tag)
                )

    pw = pull[ok_sw[pull]]
    if len(pw):
        depth = g.depth(xy[:, w] - xy[:, s])
        k = int(pw[np.argmax(depth[pw])])
        out["pull_depth"].values.append(Value(depth[k], conf_sw[k], k, **tag))
        if len(pw) >= 0.6 * len(pull):
            phase = (pw - c.reach) / max(1, c.end - c.reach)
            grid = np.linspace(0, 1, PATH_SAMPLES)
            ahead = g.along(xy[:, w] - xy[:, s])
            path = np.stack(
                [np.interp(grid, phase, ahead[pw]), np.interp(grid, phase, depth[pw])], 1
            )
            paths.setdefault(c.arm, []).append((path, c, float(np.median(conf_sw[pw]))))

    if ok_sw[c.reach]:
        reach = g.along(xy[:, w] - xy[:, s])[c.reach]
        out["reach_ahead_of_shoulder"].values.append(Value(reach, conf_sw[c.reach], c.reach, **tag))

    # Entry: the first time the hand is seen ahead of the shoulder after the recovery,
    # which happens above the water and out of an underwater camera's view.
    recovery = np.arange(c.start + 1, c.reach + 1)
    ahead = g.along(xy[:, w] - xy[:, s])
    seen = recovery[ok_sw[recovery] & (ahead[recovery] > 0)]
    if len(seen):
        k = int(seen[0])
        out["entry_ahead_of_shoulder"].values.append(Value(ahead[k], conf_sw[k], k, **tag))
        ok_nose, conf_nose = g.ok([NOSE, w])
        if ok_nose[k]:
            past_head = g.along(xy[:, w] - xy[:, NOSE])[k]
            out["entry_ahead_of_head"].values.append(Value(past_head, conf_nose[k], k, **tag))

    out["cycle_time"].values.append(
        Value(c.duration_s, float(np.median(conf_sw[pull])), c.reach, **tag)
    )


def _body_measures(g: _Geometry, c: StrokeCycle, out: dict[str, Measure]) -> None:
    xy = g.xy
    tag = {"section": c.section, "cycle_start": c.start}
    frames = np.arange(c.start, c.end + 1)
    shoulders = (xy[:, 5] + xy[:, 6]) / 2
    hips = (xy[:, 11] + xy[:, 12]) / 2
    ok_trunk, conf_trunk = g.ok([5, 6, 11, 12])

    ankles, ok_ankles, conf_ankles = [], [], []
    for leg in LEGS.values():
        ok_a, conf_a = g.ok([leg[2]])
        ankles.append(xy[:, leg[2]])
        ok_ankles.append(ok_a)
        conf_ankles.append(conf_a)
    both = ok_ankles[0] & ok_ankles[1]
    ankle = np.where(
        both[:, None],
        (ankles[0] + ankles[1]) / 2,
        np.where(ok_ankles[0][:, None], ankles[0], ankles[1]),
    )
    ok_line = ok_trunk & (ok_ankles[0] | ok_ankles[1])
    conf_line = np.minimum(
        conf_trunk, np.maximum(conf_ankles[0] * ok_ankles[0], conf_ankles[1] * ok_ankles[1])
    )

    f = frames[ok_line[frames]]
    if len(f) >= 3:
        # Straight line through shoulders, hips and ankles; its angle against travel,
        # positive when the head end is higher than the feet.
        angles = []
        for k in f:
            pts = np.stack([shoulders[k], hips[k], ankle[k]])
            pts = pts - pts.mean(axis=0)
            direction = np.linalg.svd(pts)[2][0]
            if direction @ (shoulders[k] - ankle[k]) < 0:
                direction = -direction
            angles.append(np.degrees(np.arctan2(-direction @ g.down[k], direction @ g.travel[k])))
        angles = np.array(angles)
        out["body_line_angle"].values.append(
            Value(
                float(np.median(angles)),
                float(np.median(conf_line[f])),
                _pick_median(f, angles),
                **tag,
            )
        )

    f = frames[ok_trunk[frames]]
    if len(f) >= 3:
        hip_depth = g.depth(hips - shoulders)[f]
        out["hip_depth_below_shoulders"].values.append(
            Value(
                float(np.median(hip_depth)),
                float(np.median(conf_trunk[f])),
                _pick_median(f, hip_depth),
                **tag,
            )
        )

    # Head: the ear-to-nose line against the hip-to-shoulder line. With the face toward
    # the pool floor that's 90 degrees, so report the lift away from it.
    ok_l, conf_l = g.ok([LEFT_EAR, NOSE])
    ok_r, conf_r = g.ok([RIGHT_EAR, NOSE])
    use_left = ok_l & (~ok_r | (conf_l >= conf_r))
    ear = np.where(use_left[:, None], xy[:, LEFT_EAR], xy[:, RIGHT_EAR])
    ok_head = (ok_l | ok_r) & ok_trunk
    conf_head = np.minimum(np.where(use_left, conf_l, conf_r), conf_trunk)
    f = frames[ok_head[frames]]
    if len(f) >= 3:
        face = xy[f, NOSE] - ear[f]
        body = shoulders[f] - hips[f]
        cross = body[:, 0] * face[:, 1] - body[:, 1] * face[:, 0]
        head = 90 - np.degrees(np.arctan2(cross, np.einsum("fd,fd->f", body, face)))
        out["head_angle"].values.append(
            Value(
                float(np.median(head)), float(np.median(conf_head[f])), _pick_median(f, head), **tag
            )
        )


def _kick_measures(
    g: _Geometry, c: StrokeCycle, out: dict[str, Measure], body_length: float
) -> None:
    xy = g.xy
    tag = {"section": c.section, "cycle_start": c.start}
    frames = np.arange(c.start, c.end + 1)
    min_gap = max(1, round(MIN_KICK_SPACING_S * g.pose.fps))
    beats, sizes, bends, points, confs = 0, [], [], [], []
    bend_frame = None
    for side, (hip, knee, ankle, foot) in LEGS.items():
        ok_a, conf_a = g.ok([11, 12, ankle])
        okf = frames[ok_a[frames]]
        if len(okf) < MIN_LEG_COVERAGE * len(frames):
            return  # kicks need both legs well seen through the cycle
        hips = (xy[:, 11] + xy[:, 12]) / 2
        depth = np.interp(frames, okf, g.depth(xy[:, ankle] - hips)[okf])
        for p in find_peaks(depth, min_gap):
            window = depth[max(0, p - min_gap) : p + min_gap + 1]
            if depth[p] - window.min() >= MIN_KICK_PROMINENCE:
                beats += 1
        sizes.append(np.percentile(depth, 95) - np.percentile(depth, 5))
        confs.append(float(np.median(conf_a[okf])))

        ok_k, conf_k = g.ok([hip, knee, ankle])
        fk = frames[ok_k[frames]]
        if len(fk):
            knee_angle = joint_angle(xy[:, hip], xy[:, knee], xy[:, ankle])
            k = int(fk[np.argmin(knee_angle[fk])])
            bend = 180 - knee_angle[k]
            if not bends or bend > max(bends):
                bend_frame = k
            bends.append(bend)

        big_toe, heel = foot[0], foot[2]
        ok_f, _ = g.ok([knee, ankle, big_toe, heel])
        ff = frames[ok_f[frames]]
        if len(ff) >= 3:
            point = angle_between(xy[ff, big_toe] - xy[ff, heel], xy[ff, ankle] - xy[ff, knee])
            points.append((side, float(np.median(point)), _pick_median(ff, point)))

    conf = float(min(confs))
    out["kicks_per_cycle"].values.append(Value(beats, conf, c.reach, **tag))
    size = float(np.mean(sizes))
    out["kick_size"].values.append(Value(size, conf, c.reach, **tag))
    if body_length > 0:
        out["kick_size_body"].values.append(Value(size / body_length, conf, c.reach, **tag))
    if bends:
        out["knee_bend_max"].values.append(Value(float(max(bends)), conf, bend_frame, **tag))
    for side, point, frame in points:
        out["foot_point"].values.append(Value(point, conf, frame, side=side, **tag))


def _breathing(g: _Geometry, strokes: StrokeAnalysis, out: dict[str, Measure]) -> None:
    """Experimental: breaths seen as the head rolling to the side.

    Face down, the nose sits below the ears; as the head rolls to breathe (to either side)
    the nose comes level with them. A breath is a dip of the nose's depth below the ears
    that reaches near zero. From the side we can't tell which way the head turned.
    """
    stretch = main_stretch(g.pose)
    trusted = [c for c in strokes.cycles if c.trusted]
    if stretch is None or len(trusted) < BREATH_MIN_CYCLES:
        _breath_status(out, f"needs at least {BREATH_MIN_CYCLES} trusted stroke cycles")
        return
    a, b = stretch
    ok, conf = g.ok([NOSE, LEFT_EAR, RIGHT_EAR])
    span = np.arange(a, b + 1)
    seen = span[ok[span]]
    if len(seen) < 0.5 * len(span):
        _breath_status(out, "head not seen well enough")
        return
    ears = (g.xy[:, LEFT_EAR] + g.xy[:, RIGHT_EAR]) / 2
    nose_depth = np.interp(span, seen, g.depth(g.xy[:, NOSE] - ears)[seen])
    window = max(1, round(0.3 * g.pose.fps))
    smooth = np.convolve(np.pad(nose_depth, window, mode="edge"), np.ones(window) / window, "same")
    smooth = smooth[window:-window]
    face_down = float(np.percentile(smooth, 75))
    if face_down <= 0:
        _breath_status(out, "head position unclear")
        return
    low = smooth < BREATH_ENTER * face_down
    min_len = max(1, round(BREATH_MIN_S * g.pose.fps))
    events = []
    k = 0
    while k < len(span):
        if not low[k]:
            k += 1
            continue
        end = k
        while end + 1 < len(span) and low[end + 1]:
            end += 1
        deepest = k + int(np.argmin(smooth[k : end + 1]))
        if end - k + 1 >= min_len and smooth[deepest] <= BREATH_DEEP * face_down:
            events.append(int(span[deepest]))
        k = end + 1
    if not events:
        _breath_status(out, "no head turns seen")
        return

    counts = {arm: sum(c.arm == arm for c in trusted) for arm in ("left", "right")}
    near_arm = max(counts, key=counts.get)
    arm_cycles = [c for c in trusted if c.arm == near_arm]
    for e in events:
        cycle = next((c for c in arm_cycles if c.start <= e <= c.end), None)
        if cycle is not None:
            phase = (e - cycle.start) / max(1, cycle.end - cycle.start)
            out["breath_timing"].values.append(
                Value(phase, float(conf[e]), e, near_arm, cycle.section, cycle.start)
            )
    breath_conf = float(np.median(conf[events]))
    minutes = len(span) / g.pose.fps / 60
    out["breaths_per_min"].values.append(Value(len(events) / minutes, breath_conf, events[0]))
    stroke_rate = strokes.stroke_rate_per_min
    if not np.isnan(stroke_rate):
        out["breaths_per_arm_cycle"].values.append(
            Value(len(events) / minutes / stroke_rate, breath_conf, events[0])
        )


def _breath_status(out: dict[str, Measure], status: str) -> None:
    for name in ("breath_timing", "breaths_per_min", "breaths_per_arm_cycle"):
        out[name].status = status


def _new_measures() -> dict[str, Measure]:
    defs = [
        ("cycle_time", "s", "Duration of one arm cycle."),
        (
            "elbow_min_pull",
            "deg",
            "Smallest elbow angle during the underwater pull (180 = straight arm); its curve "
            "samples the pull at 11 even steps.",
        ),
        ("elbow_mean_pull", "deg", "Mean elbow angle through the underwater pull."),
        (
            "catch_forearm_from_vertical",
            "deg",
            f"Forearm angle from straight down at the catch (upper arm {CATCH_UPPER_ARM_DEG} deg "
            f"below the travel line).",
        ),
        (
            "catch_elbow_above_wrist",
            "trunk",
            "At the catch, how far the elbow is above the wrist (negative = elbow below: dropped).",
        ),
        (
            "catch_elbow_above_hand",
            "trunk",
            "At the catch, how far the elbow is above the hand's center.",
        ),
        ("pull_depth", "trunk", "Deepest wrist position below the shoulder during the pull."),
        (
            "reach_ahead_of_shoulder",
            "trunk",
            "How far ahead of the shoulder the wrist reaches at full extension.",
        ),
        (
            "entry_ahead_of_shoulder",
            "trunk",
            "Where the hand is first seen underwater after the recovery, ahead of the shoulder.",
        ),
        (
            "entry_ahead_of_head",
            "trunk",
            "Where the hand is first seen underwater after the recovery, ahead of the nose "
            "(negative = behind it).",
        ),
        (
            "pull_shape_spread",
            "trunk",
            "How far each pull's wrist path is from that arm's average path (RMS).",
        ),
        (
            "body_line_angle",
            "deg",
            "Angle of the shoulder-hip-ankle line against the travel direction (positive = feet "
            "lower than head).",
        ),
        (
            "hip_depth_below_shoulders",
            "trunk",
            "How far the hips sit below the shoulders, measured straight down.",
        ),
        (
            "head_angle",
            "deg",
            "Head lift: the ear-to-nose line against the hip-to-shoulder line, less 90 "
            "(0 = face toward the pool floor, positive = head lifted to look forward).",
        ),
        (
            "kicks_per_cycle",
            "kicks",
            "Kick beats (both legs) during one arm cycle: about 2, 4 or 6.",
        ),
        (
            "kick_size",
            "trunk",
            "Ankle up-down range during the cycle (5th to 95th percentile), mean of both legs.",
        ),
        ("kick_size_body", "body", "Kick size as a fraction of body length (shoulders to ankles)."),
        ("knee_bend_max", "deg", "Largest knee bend in the cycle (0 = straight leg)."),
        (
            "foot_point",
            "deg",
            "Heel-to-toe line against the shin (0 = foot in line with the shin, 90 = at a right "
            "angle).",
        ),
    ]
    measures = {name: Measure(name, unit, text) for name, unit, text in defs}
    for name, unit, text in [
        (
            "breath_timing",
            "cycle",
            "When in the near arm's cycle the head turns to breathe (0 = arm straight back, then "
            "recovery, reach, pull).",
        ),
        ("breaths_per_min", "per min", "Breaths (head turns to either side) per minute."),
        (
            "breaths_per_arm_cycle",
            "per cycle",
            "Breaths per arm cycle (1 = every 2 strokes, 0.67 = every 3).",
        ),
    ]:
        measures[name] = Measure(name, unit, text, experimental=True)
    measures["body_rotation"] = Measure(
        "body_rotation",
        "deg",
        "Roll of the shoulders and hips around the body line.",
        status="needs an overhead or front clip",
    )
    return measures


def near_side(raw: WholeBodySequence) -> str | None:
    """Which arm faces the camera in a side view: the one the model scores clearly higher
    (the far arm is mostly hidden behind the body). None when they're too close to call.

    Uses the raw scores because cleanup's confidences top out at 1 for both arms.
    """
    scores = {}
    for side, (shoulder, elbow, wrist, _) in ARMS.items():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            scores[side] = float(np.nanmedian(raw.keypoints[:, [shoulder, elbow, wrist], 2]))
    if any(np.isnan(x) for x in scores.values()):
        return None
    left, right = scores["left"], scores["right"]
    if abs(left - right) < NEAR_SIDE_MIN_GAP:
        return None
    return "left" if left > right else "right"


def measure_technique(
    pose: CleanPose,
    strokes: StrokeAnalysis,
    horizon: np.ndarray | None = None,
    horizontal_source: str = "frame horizontal",
    distance_m: float | None = None,
    time_s: float | None = None,
    near_side: str | None = None,
) -> TechniqueReport:
    """All technique measures for one clip. `horizon` is the travel direction per frame
    (radians, oriented frame); see `aquatrack.analysis.horizon.horizontal`."""
    if horizon is None:
        horizon = np.zeros(len(pose))
    g = _Geometry(pose, horizon)
    out = _new_measures()
    trusted = [c for c in strokes.cycles if c.trusted and c.reach is not None]

    shoulders = (pose.xy[:, 5] + pose.xy[:, 6]) / 2
    ankles = (pose.xy[:, 15] + pose.xy[:, 16]) / 2
    ok_len, _ = g.ok([5, 6, 15, 16])
    lengths = np.linalg.norm(shoulders - ankles, axis=1)[ok_len] / pose.trunk[ok_len]
    body_length = float(np.median(lengths)) if len(lengths) else float("nan")

    paths: dict[str, list] = {}
    for c in trusted:
        _arm_measures(g, c, out, paths)
        _body_measures(g, c, out)
        _kick_measures(g, c, out, body_length)

    for arm, items in paths.items():
        if len(items) < 2:
            continue
        mean = np.mean([p for p, _, _ in items], axis=0)
        for path, c, conf in items:
            rms = float(np.sqrt(((path - mean) ** 2).sum(axis=1).mean()))
            out["pull_shape_spread"].values.append(
                Value(rms, conf, c.reach, side=arm, section=c.section, cycle_start=c.start)
            )

    _breathing(g, strokes, out)

    if near_side:
        for name in ARM_GEOMETRY:
            out[name].prefer_side = near_side
            for v in out[name].values:
                if v.side and v.side != near_side:
                    v.confidence *= FAR_ARM_CONFIDENCE

    balance = {}
    for name in ("cycle_time", "pull_depth", "elbow_min_pull"):
        left, right = out[name].median(side="left"), out[name].median(side="right")
        if not np.isnan(left) and not np.isnan(right):
            balance[name] = {
                "left": _r(left),
                "right": _r(right),
                "left_minus_right": _r(left - right),
            }
    times = out["cycle_time"].numbers()
    if len(times) >= 3:
        balance["cycle_time_cv"] = _r(np.std(times) / np.mean(times))

    session = {}
    if distance_m and time_s:
        speed = distance_m / time_s
        session = {
            "distance_m": distance_m,
            "time_s": time_s,
            "speed_m_per_s": _r(speed),
            "pace_per_100m_s": _r(100 / speed),
        }
        rate = strokes.stroke_rate_per_min
        if not np.isnan(rate):
            session["distance_per_cycle_m"] = _r(speed * 60 / rate)

    return TechniqueReport(out, horizontal_source, near_side, balance, session)
