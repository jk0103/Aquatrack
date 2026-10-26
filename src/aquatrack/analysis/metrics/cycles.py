"""Arm stroke cycles, stroke rate and swim sections from a cleaned whole-body sequence.

Each arm's cycle comes from its angle around the shoulder, measured from the body line
(hip to shoulder): 0 when the arm points straight ahead, pi when it points back along the
body. The angle turns once per stroke for freestyle, backstroke and butterfly, so cycles
are counted from its unwrapped phase rather than from raw wrist height. A cycle starts
and ends when the arm points straight back (end of the push), and its reach is the frame
where the hand is furthest forward.

Breaststroke arms sweep instead of turning all the way around; they need another method.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from aquatrack.analysis.pose.cleanup import (
    L_SHOULDER,
    L_WRIST,
    R_SHOULDER,
    R_WRIST,
    CleanPose,
    Fix,
)

ARMS = {"left": (L_SHOULDER, L_WRIST), "right": (R_SHOULDER, R_WRIST)}

# Backward steps up to this are allowed (the pull moves ~15 degrees per frame at 25 fps).
# A bigger jump is read as forward motion: the arm recovering out of view, above the water.
MAX_BACKWARD = np.pi / 2
MIN_TRUSTED_FRACTION = 0.6  # of a cycle's frames with reliable shoulder and wrist
MIN_RELIABLE_CONFIDENCE = 0.3
CYCLE_SECONDS = (0.6, 4.0)  # plausible duration of one arm cycle
SECTION_NAMES = ("start", "middle", "end")


@dataclass
class StrokeCycle:
    """One arm cycle. Frames are indices into the CleanPose sequence."""

    arm: str
    start: int
    end: int
    reach: int | None
    duration_s: float
    trusted: bool
    reason: str = ""
    section: str = ""


@dataclass
class Section:
    name: str
    start: int
    end: int


@dataclass
class StrokeAnalysis:
    cycles: list[StrokeCycle]
    sections: list[Section]
    # Cycles per minute for each arm, from trusted cycles; NaN when there are none.
    rate_per_min: dict[str, float] = field(default_factory=dict)

    @property
    def stroke_rate_per_min(self) -> float:
        """Stroke cycles per minute: the mean of the arms that have a rate."""
        rates = [r for r in self.rate_per_min.values() if not np.isnan(r)]
        return float(np.mean(rates)) if rates else float("nan")

    def to_dict(self, pose: CleanPose) -> dict:
        """JSON-ready, with source video frame numbers and seconds alongside."""

        def frame(i):
            return None if i is None else int(pose.frame_indices[i])

        source_fps = pose.fps * (
            (pose.frame_indices[1] - pose.frame_indices[0]) if len(pose) > 1 else 1
        )

        def seconds(i):
            return None if i is None else round(frame(i) / source_fps, 3)

        return {
            "flipped": pose.flipped,
            "stroke_rate_per_min": _round(self.stroke_rate_per_min),
            "rate_per_min": {arm: _round(r) for arm, r in self.rate_per_min.items()},
            "cycles": [
                {
                    **asdict(c),
                    "start_frame": frame(c.start),
                    "end_frame": frame(c.end),
                    "reach_frame": frame(c.reach),
                    "start_s": seconds(c.start),
                    "end_s": seconds(c.end),
                    "reach_s": seconds(c.reach),
                    "duration_s": round(c.duration_s, 3),
                }
                for c in self.cycles
            ],
            "sections": [
                {**asdict(s), "start_frame": frame(s.start), "end_frame": frame(s.end)}
                for s in self.sections
            ],
        }

    def save(self, path: str | Path, pose: CleanPose) -> Path:
        path = Path(path)
        path.write_text(json.dumps(self.to_dict(pose), indent=2))
        return path


def _round(value: float) -> float | None:
    return None if np.isnan(value) else round(float(value), 2)


def default_cycles_path(video_path: str | Path) -> Path:
    video_path = Path(video_path)
    return video_path.with_name(f"{video_path.stem}.cycles.json")


def arm_angle(pose: CleanPose, arm: str) -> tuple[np.ndarray, np.ndarray]:
    """Per frame: the arm's angle from the body line (radians, NaN when unknown), and how
    reliable it is (0-1; 0 when either point was filled in or missing)."""
    shoulder, wrist = ARMS[arm]
    axis = pose.body_axis()
    normal = np.stack([-axis[:, 1], axis[:, 0]], axis=1)
    arm_vec = pose.xy[:, wrist] - pose.xy[:, shoulder]
    angle = np.arctan2(np.einsum("fd,fd->f", arm_vec, normal), np.einsum("fd,fd->f", arm_vec, axis))
    reliable = np.minimum(pose.confidence[:, shoulder], pose.confidence[:, wrist])
    guessed = ((pose.flags[:, shoulder] | pose.flags[:, wrist]) & Fix.FILLED) > 0
    reliable = np.where(guessed | np.isnan(angle), 0.0, reliable)
    return angle, reliable


def unwrap_phase(angle: np.ndarray) -> np.ndarray:
    """Unwrapped arm phase that grows by 2*pi per stroke, NaN where the angle is unknown.

    The rotation direction depends on which side the camera films from, so it is taken
    from the data: the sign of the summed small frame-to-frame changes.
    """
    phase = np.full_like(angle, np.nan)
    valid = np.nonzero(~np.isnan(angle))[0]
    if len(valid) < 2:
        return phase
    steps = np.angle(np.exp(1j * np.diff(angle[valid])))
    small = np.abs(steps) < np.pi / 2
    sign = 1.0 if steps[small].sum() >= 0 else -1.0
    a = sign * angle[valid]
    deltas = np.mod(np.diff(a) + MAX_BACKWARD, 2 * np.pi) - MAX_BACKWARD
    phase[valid] = a[0] + np.concatenate([[0.0], np.cumsum(deltas)])
    return phase


def _boundaries(phase: np.ndarray) -> list[float]:
    """Fractional frames where the arm passes straight back (phase = pi + 2*pi*k)."""
    valid = np.nonzero(~np.isnan(phase))[0]
    if len(valid) < 2:
        return []
    # Never count a boundary twice when the arm wobbles back across it.
    peak = np.maximum.accumulate(phase[valid])
    turns = np.floor((peak - np.pi) / (2 * np.pi))
    found = []
    for k in range(1, len(valid)):
        for turn in range(int(turns[k - 1]) + 1, int(turns[k]) + 1):
            target = np.pi + 2 * np.pi * turn
            i, j = valid[k - 1], valid[k]
            t = (target - peak[k - 1]) / (peak[k] - peak[k - 1])
            found.append(i + t * (j - i))
    return found


def find_cycles(pose: CleanPose, arm: str) -> list[StrokeCycle]:
    angle, reliable = arm_angle(pose, arm)
    # Only observed points: a gap filled in a straight line from hip to reach runs through
    # the body, which would read as the arm turning backward.
    phase = unwrap_phase(np.where(reliable > 0, angle, np.nan))
    bounds = _boundaries(phase)
    shoulder, wrist = ARMS[arm]
    axis = pose.body_axis()
    forward = np.einsum("fd,fd->f", pose.xy[:, wrist] - pose.xy[:, shoulder], axis)

    cycles = []
    for a, b in zip(bounds[:-1], bounds[1:], strict=True):
        start, end = round(a), round(b)
        duration = float((b - a) / pose.fps)
        frames = np.arange(start, end + 1)
        ok = reliable[frames] >= MIN_RELIABLE_CONFIDENCE
        reach = None
        if ok.any():
            candidates = frames[ok]
            reach = int(candidates[np.nanargmax(forward[candidates])])
        reason = ""
        if ok.mean() < MIN_TRUSTED_FRACTION:
            reason = f"only {ok.mean():.0%} of frames have a reliable shoulder and wrist"
        elif not CYCLE_SECONDS[0] <= duration <= CYCLE_SECONDS[1]:
            reason = f"{duration:.2f} s is outside {CYCLE_SECONDS[0]}-{CYCLE_SECONDS[1]} s"
        cycles.append(
            StrokeCycle(
                arm=arm,
                start=start,
                end=end,
                reach=reach,
                duration_s=duration,
                trusted=not reason,
                reason=reason,
            )
        )
    return cycles


def find_sections(pose: CleanPose, n: int = len(SECTION_NAMES)) -> list[Section]:
    """Split the frames where the swimmer is seen into equal-time thirds."""
    seen = np.nonzero(np.isfinite(pose.trunk))[0]
    if len(seen) == 0:
        return []
    edges = np.linspace(seen[0], seen[-1] + 1, n + 1).round().astype(int)
    return [Section(SECTION_NAMES[i], int(edges[i]), int(edges[i + 1] - 1)) for i in range(n)]


def analyze_strokes(pose: CleanPose) -> StrokeAnalysis:
    sections = find_sections(pose)
    cycles, rates = [], {}
    for arm in ARMS:
        arm_cycles = find_cycles(pose, arm)
        durations = [c.duration_s for c in arm_cycles if c.trusted]
        rates[arm] = 60.0 / float(np.median(durations)) if durations else float("nan")
        cycles += arm_cycles
    for c in cycles:
        middle = c.reach if c.reach is not None else (c.start + c.end) // 2
        c.section = next((s.name for s in sections if s.start <= middle <= s.end), "")
    cycles.sort(key=lambda c: c.start)
    return StrokeAnalysis(cycles=cycles, sections=sections, rate_per_min=rates)
