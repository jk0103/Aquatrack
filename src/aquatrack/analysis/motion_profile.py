"""The motion profile: one clip's movement in a form that can be reasoned about.

Built from the cleaned pose, the stroke cycles and the stored AnalysisResult, all of which
stay the authority for every number here. It is what the motion interpreter (advice.py) is
given instead of raw keypoints:

  - the measured metrics with their own status and limits (the same values the result shows)
  - each stroke cycle of the followed arm with its events and phase durations
  - joint paths in the BODY frame, sampled at the same points of every cycle
  - elbow and knee angles along the cycle
  - what differs from cycle to cycle: per-cycle series with spread, trend and alternation
  - what the tracker could not see, per joint, and how exact any of it is

Everything is deterministic: the same pose gives the same profile, and its hash identifies
which measurements an interpretation was made from. Developed and checked in
`experiments/gpt_motion_advice/` (synthetic swimmers and three public clips).
"""

import hashlib
import json

import numpy as np

from aquatrack.analysis.metrics.cycles import StrokeAnalysis
from aquatrack.analysis.pose.cleanup import DROPPED, CleanPose, Fix
from aquatrack.contracts import AnalysisResult

PROFILE_VERSION = "1.0"
SAMPLES = 12  # per stroke cycle
MAX_CYCLES = 6
JOINTS = {
    "shoulder": (5, 6),
    "elbow": (7, 8),
    "wrist": (9, 10),
    "hip": (11, 12),
    "knee": (13, 14),
    "ankle": (15, 16),
}
FEATURES = (
    "cycle_duration_s",
    "front_phase_s",
    "catch_to_mid_pull_s",
    "mid_pull_to_exit_s",
    "exit_to_next_reach_s",
    "elbow_angle_at_mid_pull_deg",
    "min_elbow_angle_in_cycle_deg",
    "wrist_deepest_below_shoulder",
    "wrist_furthest_ahead_of_shoulder",
    "hip_below_shoulder_line",
    "ankle_below_hip_line",
    "knee_angle_range_deg",
    "head_ahead_of_shoulder",
    "body_line_vs_picture_horizontal_deg",
)


def _series(values: list[float | None]) -> dict:
    """Per-cycle values with what is needed to compare cycles."""
    v = np.array([np.nan if x is None else x for x in values], dtype=float)
    listed = [None if not np.isfinite(x) else round(float(x), 2) for x in v]
    ok = v[np.isfinite(v)]
    if len(ok) < 2:
        return {"per_cycle": listed}
    slope = float(np.polyfit(np.nonzero(np.isfinite(v))[0], ok, 1)[0]) if len(ok) >= 3 else None
    steps = np.diff(ok)
    turns = float(np.mean(np.sign(steps[:-1]) != np.sign(steps[1:]))) if len(steps) >= 3 else None
    return {
        "per_cycle": listed,
        "median": round(float(np.median(ok)), 2),
        "min": round(float(ok.min()), 2),
        "max": round(float(ok.max()), 2),
        "trend_per_cycle": None if slope is None else round(slope, 3),
        "share_of_direction_reversals": None if turns is None else round(turns, 2),
    }


def _angle(a, b, c) -> float | None:
    """Angle at b (degrees) between points a and c."""
    u, v = a - b, c - b
    d = float(np.linalg.norm(u) * np.linalg.norm(v))
    if not np.isfinite(d) or d == 0:
        return None
    return float(np.degrees(np.arccos(np.clip(u @ v / d, -1, 1))))


def _metrics(result: AnalysisResult) -> list[dict]:
    return [
        {
            "key": m.key,
            "label": m.label,
            "unit": m.unit,
            "description": m.description,
            "status": m.status.value,
            "value": m.value,
            "low_25pct": m.low,
            "high_75pct": m.high,
            "n_cycles": m.n_cycles,
            "arm_side": m.side,
            "why_limited_or_unavailable": m.reason,
            "limitations": getattr(m, "limitations", []),
            "per_cycle": [{"t_s": s.t_s, "value": s.value} for s in m.samples],
        }
        for m in result.metrics
    ]


def followed_arm(result: AnalysisResult, strokes: StrokeAnalysis) -> str:
    if result.stroke.counted_arm:
        return result.stroke.counted_arm
    return max(strokes.pulls, key=lambda a: len(strokes.pulls[a]), default="left")


def _motion(pose: CleanPose, strokes: StrokeAnalysis, arm: str) -> dict:
    fps, units = pose.fps, pose.body_units()
    side = 0 if arm == "left" else 1
    usable = ((pose.flags & int(DROPPED)) == 0) & np.isfinite(pose.xy[..., 0])
    filled = (pose.flags & int(Fix.FILLED)) > 0
    idx = {name: pair[side] for name, pair in JOINTS.items()}
    axis = pose.body_axis()
    pulls = strokes.pulls.get(arm, [])
    by_reach = {p.reach: n for n, p in enumerate(pulls)}
    cycles = [c for c in strokes.cycles if c.arm == arm][:MAX_CYCLES]

    def sec(frame) -> float:
        return round(float(frame) / fps, 2)

    def point(i, name):
        k = idx[name]
        return units[i, k] if usable[i, k] else None

    rows, feats = [], {k: [] for k in FEATURES}
    for c in cycles:
        closing = pulls[by_reach[c.reach]] if c.reach in by_reach else None
        opening = (
            pulls[by_reach[c.reach] - 1] if closing is not None and by_reach[c.reach] > 0 else None
        )
        frames = np.linspace(c.start, c.end, SAMPLES, endpoint=False).round().astype(int)
        samples, got = [], {k: [] for k in ("elbow", "depth", "ahead", "hip", "ankle", "knee")}
        heads, tilts = [], []
        for n, i in enumerate(frames):
            p = {name: point(i, name) for name in idx}
            sh, hip = p["shoulder"], p["hip"]
            row = {"phase": round(n / SAMPLES, 2), "t_s": sec(i)}
            for name, origin, label in (
                ("elbow", sh, "elbow_rel_shoulder"),
                ("wrist", sh, "wrist_rel_shoulder"),
                ("knee", hip, "knee_rel_hip"),
                ("ankle", hip, "ankle_rel_hip"),
            ):
                row[label] = (
                    None
                    if p[name] is None or origin is None
                    else [
                        round(float(p[name][0] - origin[0]), 2),
                        round(float(p[name][1] - origin[1]), 2),
                    ]
                )
            elbow = (
                None
                if any(p[k] is None for k in ("shoulder", "elbow", "wrist"))
                else _angle(p["shoulder"], p["elbow"], p["wrist"])
            )
            knee = (
                None
                if any(p[k] is None for k in ("hip", "knee", "ankle"))
                else _angle(p["hip"], p["knee"], p["ankle"])
            )
            row["elbow_angle_deg"] = None if elbow is None else round(elbow)
            row["knee_angle_deg"] = None if knee is None else round(knee)
            row["interpolated_points"] = [name for name in idx if filled[i, idx[name]]]
            row["unusable_points"] = [name for name in idx if not usable[i, idx[name]]]
            samples.append(row)
            if elbow is not None:
                got["elbow"].append(elbow)
            if row["wrist_rel_shoulder"]:
                got["ahead"].append(row["wrist_rel_shoulder"][0])
                got["depth"].append(row["wrist_rel_shoulder"][1])
            if sh is not None and hip is not None:
                got["hip"].append(float(hip[1] - sh[1]))
            if row["ankle_rel_hip"]:
                got["ankle"].append(row["ankle_rel_hip"][1])
            if knee is not None:
                got["knee"].append(knee)
            if usable[i, 0] and sh is not None:
                heads.append(float(units[i, 0][0] - sh[0]))
            if np.isfinite(axis[i]).all():
                tilts.append(float(np.degrees(np.arctan2(-axis[i, 1], axis[i, 0]))))
        events = {}
        if closing is not None:
            events = {
                "reach_s": sec(closing.reach),
                "catch_begins_s": sec(closing.start),
                "wrist_mid_pull_s": sec(closing.mid),
                "pull_followed_until_s": sec(closing.exit),
                "pull_followed_to_deg_behind": round(closing.exit_angle_deg),
            }
        at_start = {name: point(int(c.start), name) for name in ("shoulder", "elbow", "wrist")}
        feats["cycle_duration_s"].append(c.duration_s)
        feats["front_phase_s"].append(
            None if closing is None else (closing.start - closing.reach) / fps
        )
        feats["catch_to_mid_pull_s"].append(
            None if closing is None else (closing.mid - closing.start) / fps
        )
        feats["mid_pull_to_exit_s"].append(
            None if opening is None else (opening.exit - opening.mid) / fps
        )
        feats["exit_to_next_reach_s"].append(
            None if opening is None or closing is None else (closing.reach - opening.exit) / fps
        )
        feats["elbow_angle_at_mid_pull_deg"].append(
            None
            if any(v is None for v in at_start.values())
            else _angle(at_start["shoulder"], at_start["elbow"], at_start["wrist"])
        )
        feats["min_elbow_angle_in_cycle_deg"].append(min(got["elbow"]) if got["elbow"] else None)
        feats["wrist_deepest_below_shoulder"].append(max(got["depth"]) if got["depth"] else None)
        feats["wrist_furthest_ahead_of_shoulder"].append(
            max(got["ahead"]) if got["ahead"] else None
        )
        feats["hip_below_shoulder_line"].append(
            float(np.median(got["hip"])) if got["hip"] else None
        )
        feats["ankle_below_hip_line"].append(
            float(np.median(got["ankle"])) if got["ankle"] else None
        )
        feats["knee_angle_range_deg"].append(
            max(got["knee"]) - min(got["knee"]) if got["knee"] else None
        )
        feats["head_ahead_of_shoulder"].append(float(np.median(heads)) if heads else None)
        feats["body_line_vs_picture_horizontal_deg"].append(
            float(np.median(tilts)) if tilts else None
        )
        rows.append(
            {
                "cycle": len(rows) + 1,
                "start_s": sec(c.start),
                "end_s": sec(c.end),
                "duration_s": round(c.duration_s, 2),
                "timed_from": c.timing,
                "trusted": c.trusted,
                "why_not_trusted": c.reason,
                "events_of_closing_pull": events,
                "samples": samples,
            }
        )

    tracking = {}
    gap = max(1, round(0.3 * fps))
    for name, k in idx.items():
        gone = np.concatenate([~usable[:, k], [False]])
        runs, run = [], None
        for i, g in enumerate(gone):
            if g and run is None:
                run = i
            elif not g and run is not None:
                if i - run >= gap:
                    runs.append([sec(run), sec(i)])
                run = None
        flags = pose.flags[:, k]
        tracking[name] = {
            "usable_share": round(float(usable[:, k].mean()), 2),
            "unusable_stretches_s": runs[:8],
            "dropped_low_score": int(((flags & int(Fix.LOW_SCORE)) > 0).sum()),
            "dropped_one_frame_jump": int(((flags & int(Fix.SPIKE)) > 0).sum()),
            "dropped_anatomically_impossible": int(((flags & int(Fix.IMPOSSIBLE)) > 0).sum()),
            "left_right_swapped_back": int(((flags & int(Fix.SWAPPED)) > 0).sum()),
            "interpolated": int(filled[:, k].sum()),
        }
    return {
        "arm_followed": arm,
        "frame": "Body frame, in trunk lengths (shoulder-to-hip distance). x is along the body "
        "toward the head; y is perpendicular to the body line, positive toward the swimmer's "
        "front (downward for a swimmer lying face down). The frame turns with the body, so a "
        "tilted camera does not change these numbers; body_line_vs_picture_horizontal_deg is "
        "the one value that includes camera tilt.",
        "phase": f"A cycle runs from one mid-pull to the next and is sampled at {SAMPLES} "
        "equally spaced moments; phase 0 is the mid-pull that starts it.",
        "timing_note": "A cycle's start_s, end_s and duration_s come from one event, named by "
        "timed_from: 'upper_arm' is the upper arm passing straight down (the shoulder's "
        "turnover, which does not depend on elbow bend); 'wrist' is the wrist passing under "
        "the shoulder. The events of a pull (reach, catch begins, wrist mid-pull, end of the "
        "followed pull) are always wrist events. When the elbow bend changes from stroke to "
        "stroke the wrist events shift against the upper-arm cycle: that is information about "
        "the arm's shape, not a measurement fault.",
        "uncertainty": {
            "timing_resolution_s": round(1 / fps, 3),
            "point_noise_trunk_lengths": 0.05,
            "angle_noise_deg_typical_and_90th_percentile": [2.4, 7],
            "view": "One side-on underwater camera: movement toward or away from the camera is "
            "not seen, the far arm is mostly hidden, and the above-water recovery cannot be "
            "checked.",
        },
        "cycles": rows,
        "cycle_to_cycle": {k: _series(v) for k, v in feats.items()},
        "tracking_of_followed_side": tracking,
    }


def build(pose: CleanPose, strokes: StrokeAnalysis, result: AnalysisResult) -> dict:
    """The profile of one analysed clip. `pose` and `strokes` must come from the same raw
    pose as `result` (cleaning and cycle detection are deterministic)."""
    quality = result.quality.model_dump(mode="json")
    return {
        "profile_version": PROFILE_VERSION,
        "session": {
            "stroke": result.session.stroke,
            "camera": result.session.camera,
            "distance": result.session.distance,
        },
        "clip": {
            "duration_s": result.timing.clip_duration_s,
            "fps": result.video.fps,
            "swim_start_s": result.timing.swim_start_s,
            "swim_end_s": result.timing.swim_end_s,
        },
        "stroke_cycles": {
            "measurable": result.stroke.measurable,
            "why_not": result.stroke.reason,
            "counted_arm": result.stroke.counted_arm,
            "cycles": [c.model_dump(mode="json") for c in result.stroke.cycles],
        },
        "tracking_quality": {
            k: quality[k]
            for k in ("grade", "summary", "notes", "warnings", "reasons")
            if k in quality
        },
        "metrics": _metrics(result),
        "not_measurable": [u.model_dump(mode="json") for u in result.unavailable],
        "motion": _motion(pose, strokes, followed_arm(result, strokes)),
    }


def digest(profile: dict) -> str:
    """Identifies the exact measurements an interpretation was made from."""
    return hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()
