"""Arm stroke cycles, stroke rate and swim sections from a cleaned whole-body sequence.

Each arm's cycle comes from its angle around the shoulder, measured from the body line
(hip to shoulder): 0 when the arm points straight ahead, 90 degrees when it points straight
down under the shoulder (mid-pull), 180 when it points back along the body.

A cycle runs from one mid-pull to the next: the moment the arm passes straight down. That
moment is used because it is the one part of the stroke an underwater side camera sees for
both arms. The end of the push is hidden behind the body for the far arm, and the recovery
is above the water, where the pose model still draws an arm (often swinging backward under
the body) that nobody can check. Counting from the unwrapped angle, as before, let those
drawn-in recoveries cancel real pulls (two cycles merged) or add false ones (a cycle split).

Each mid-pull event belongs to a `Pull`: reach (hand furthest forward) -> start (the arm
leaves the front) -> mid-pull -> exit (the last frame the arm was followed moving back). Arm
geometry is only read from start to exit: while the arm is still stretched in front there is
no movement to back the model's points up, however long it stays there.

Breaststroke arms sweep instead of turning all the way around; they need another method.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from aquatrack.analysis.pose.cleanup import (
    L_ELBOW,
    L_SHOULDER,
    L_WRIST,
    R_ELBOW,
    R_SHOULDER,
    R_WRIST,
    CleanPose,
    Fix,
)

ARMS = {"left": (L_SHOULDER, L_WRIST), "right": (R_SHOULDER, R_WRIST)}
ELBOWS = {"left": L_ELBOW, "right": R_ELBOW}

FRONT_MAX = np.radians(45)  # the arm counts as "in front" within this of straight ahead
MID_PULL = np.radians(90)  # the event: the arm passes straight down
CONFIRM = np.radians(120)  # one frame this far back confirms a pull (or two frames past 90)
MAX_EVENT_GAP_S = 0.25  # the crossing must be seen between frames no further apart
MAX_PULL_SPEED = np.radians(900)  # per second; a sprint pull turns about 500
REVERSED_MIN_SHARE = 0.3  # net backward share of all small angle changes
MAX_WOBBLE = np.radians(15)  # backward wobble allowed while a pull is still followed
MIN_TRUSTED_FRACTION = 0.6  # of a cycle's underwater frames with reliable shoulder and wrist
MIN_RELIABLE_CONFIDENCE = 0.3
# A cycle in which the arm was not seen at all for this share of its length cannot be told
# from two cycles with the stroke between them hidden (2026-11-27). In the real clips the
# longest unseen stretch of a trusted cycle was 15% of it; a recovery the model does not draw
# is at most about 40%.
MAX_UNSEEN_SHARE = 0.45
CYCLE_SECONDS = (0.6, 4.0)  # plausible duration of one arm cycle
# A cycle much shorter or longer than the clip's typical one is a fragment or two merged.
TYPICAL_RATIO = (0.6, 1.6)
MIN_CYCLES_FOR_TYPICAL = 3
SECTION_NAMES = ("start", "middle", "end")
SECTION_MAX_GAP_S = 1.0  # longer gaps split the clip; sections cover the longest part


@dataclass
class Pull:
    """One underwater pull of one arm. Frames are indices into the CleanPose sequence."""

    arm: str
    reach: int  # hand furthest forward before the pull
    start: int  # last frame in front (within FRONT_MAX): from here on the arm is pulling
    mid: float  # fractional frame where the arm passes straight down
    exit: int  # last frame the arm was followed moving back
    exit_angle_deg: float  # how far back it was followed (180 = straight back)
    # Fractional frame where the UPPER arm (shoulder to elbow) passes straight down, when the
    # elbow was seen on both sides of that moment. Used for cycle time: unlike the wrist, it
    # does not move when the swimmer bends the elbow more or less from one stroke to the next.
    mid_upper: float | None = None
    # Frames between this pull and the previous one where the arm was found past straight
    # down after being in front, but the crossing itself was not seen: a stroke that happened
    # and could not be counted.
    missed_before: list[int] = field(default_factory=list)


@dataclass
class StrokeCycle:
    """One arm cycle, mid-pull to mid-pull. Frames are indices into the CleanPose sequence.

    `start`, `end` and `duration_s` are all taken from the event named by `timing`: the upper
    arm passing straight down ("upper_arm") or the wrist passing under the shoulder ("wrist").

    `reach` is the reach of the pull that ends the cycle, and `pull_end` that pull's exit
    (after `end`): together they bound one whole underwater pull for arm measures.
    """

    arm: str
    start: int
    end: int
    reach: int | None
    duration_s: float
    trusted: bool
    reason: str = ""
    section: str = ""
    pull_start: int | None = None  # where that pull leaves the front (after `reach`)
    pull_end: int | None = None
    # "merged" (looks like two cycles with a pull not seen), "fragment", "hidden", "" (fine)
    kind: str = ""
    # What `duration_s` was timed from: "upper_arm" (both ends), else "wrist".
    timing: str = "wrist"


@dataclass
class PartialCycle:
    """Arm movement at the edge of the clip that is not a whole cycle."""

    arm: str
    start: int
    end: int


@dataclass
class Section:
    name: str
    start: int
    end: int


@dataclass
class StrokeAnalysis:
    cycles: list[StrokeCycle]
    sections: list[Section]
    pulls: dict[str, list[Pull]] = field(default_factory=dict)
    partial: list[PartialCycle] = field(default_factory=list)
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


def _reversed(angle: np.ndarray) -> bool:
    valid = np.nonzero(~np.isnan(angle))[0]
    if len(valid) < 2:
        return False
    steps = np.angle(np.exp(1j * np.diff(angle[valid])))
    small = steps[np.abs(steps) < np.pi / 2]
    return bool(small.sum() < -REVERSED_MIN_SHARE * np.abs(small).sum())


def upper_arm_angle(pose: CleanPose, arm: str) -> np.ndarray:
    """Per frame: the upper arm's angle from the body line, in the same sense as `arm_angle`
    (NaN where the shoulder or elbow was filled in, missing or unreliable)."""
    shoulder, elbow = ARMS[arm][0], ELBOWS[arm]
    axis = pose.body_axis()
    normal = np.stack([-axis[:, 1], axis[:, 0]], axis=1)
    vec = pose.xy[:, elbow] - pose.xy[:, shoulder]
    angle = np.arctan2(np.einsum("fd,fd->f", vec, normal), np.einsum("fd,fd->f", vec, axis))
    ok = np.minimum(pose.confidence[:, shoulder], pose.confidence[:, elbow])
    guessed = ((pose.flags[:, shoulder] | pose.flags[:, elbow]) & Fix.FILLED) > 0
    return np.where(guessed | (ok < MIN_RELIABLE_CONFIDENCE), np.nan, angle)


def _upper_mid(upper: np.ndarray, pull: "Pull", max_gap: int) -> float | None:
    """Where the upper arm passes straight down inside this pull: the crossing nearest the
    wrist's, seen between two frames no further apart than an event may be."""
    seen = np.nonzero(~np.isnan(upper[pull.reach : pull.exit + 1]))[0] + pull.reach
    best = None
    for p, k in zip(seen[:-1], seen[1:], strict=True):
        if (
            k - p > max_gap
            or not (upper[p] < MID_PULL <= upper[k])
            or upper[k] - upper[p] > np.pi / 2
        ):
            continue
        mid = p + (MID_PULL - upper[p]) / (upper[k] - upper[p]) * (k - p)
        if best is None or abs(mid - pull.mid) < abs(best - pull.mid):
            best = float(mid)
    return best


def pull_angle(angle: np.ndarray) -> np.ndarray:
    """The arm angle with the pull direction positive (0 ahead -> 90 down -> 180 back).

    In the oriented frame an upright camera sees the pull pass below the body, which is
    already the positive direction. Only a clip that clearly turns the other way (filmed
    from overhead, or upside down) is reversed: when most of the small frame-to-frame
    changes run backward.
    """
    return -angle if _reversed(angle) else angle


def find_pulls(pose: CleanPose, arm: str) -> list[Pull]:
    """Underwater pulls of one arm, from observed points only.

    A pull is counted when the arm has been in front and then passes straight down, seen on
    both sides of that moment, and is then followed further back. The arm has to return to
    the front before the next pull can count, so a recovery the model draws backward under
    the body, or a wobble, never adds or removes one.
    """
    angle, reliable = arm_angle(pose, arm)
    observed = np.where(reliable > 0, angle, np.nan)
    a = pull_angle(observed)
    upper = upper_arm_angle(pose, arm)
    upper = -upper if _reversed(observed) else upper
    seen = np.nonzero(~np.isnan(a))[0]
    shoulder, wrist = ARMS[arm]
    forward = np.einsum("fd,fd->f", pose.xy[:, wrist] - pose.xy[:, shoulder], pose.body_axis())
    max_gap = max(1, round(MAX_EVENT_GAP_S * pose.fps))

    pulls: list[Pull] = []
    missed: list[int] = []  # crossings that happened unseen since the last counted pull
    armed, front_from = False, None
    for n in range(len(seen)):
        k = seen[n]
        if abs(a[k]) <= FRONT_MAX:
            if not armed:
                armed, front_from = True, int(k)
            continue
        if not armed or n == 0 or a[k] < MID_PULL:
            continue
        armed = False  # past straight down: nothing more counts until the arm is in front again
        # The last frame before the crossing, skipping a stray point or two.
        before = [q for q in seen[max(0, n - 3) : n] if -FRONT_MAX <= a[q] < MID_PULL]
        crossing_seen = bool(before) and k - before[-1] <= max_gap
        if crossing_seen:
            p = before[-1]
            # no arm turns that fast: one of the two points is not this arm
            crossing_seen = (a[k] - a[p]) / ((k - p) / pose.fps) <= MAX_PULL_SPEED
        # Follow the arm back for as long as it keeps going.
        exit_frame, m = int(k), n
        while (
            m + 1 < len(seen)
            and seen[m + 1] - seen[m] <= max_gap
            and a[seen[m + 1]] >= a[exit_frame] - MAX_WOBBLE
            and a[seen[m + 1]] >= MID_PULL
        ):
            m += 1
            if a[seen[m]] > a[exit_frame]:
                exit_frame = int(seen[m])
        followed_back = not (a[exit_frame] < CONFIRM and m == n)
        if not crossing_seen:
            # The arm was in front, and is now past straight down without the passing itself
            # having been seen. If it is then followed further back like any pull, a stroke
            # happened here that cannot be timed; a stray point or a recovery the model drew
            # under the body is not followed back and leaves no mark.
            if followed_back:
                missed.append(int(k))
            continue
        if not followed_back:
            continue  # one stray frame past straight down
        mid = p + (MID_PULL - a[p]) / (a[k] - a[p]) * (k - p)
        front = seen[(seen >= front_from) & (seen < k) & (np.abs(a[seen]) <= FRONT_MAX)]
        ok = front[reliable[front] >= MIN_RELIABLE_CONFIDENCE]
        reach = int((ok if len(ok) else front)[np.nanargmax(forward[ok if len(ok) else front])])
        start = int(front[front >= reach][-1]) if (front >= reach).any() else reach
        pull = Pull(arm, reach, start, float(mid), exit_frame, float(np.degrees(a[exit_frame])))
        pull.mid_upper = _upper_mid(upper, pull, max_gap)
        pull.missed_before, missed = missed, []
        pulls.append(pull)
    return pulls


def find_cycles(pose: CleanPose, arm: str, pulls: list[Pull] | None = None) -> list[StrokeCycle]:
    pulls = find_pulls(pose, arm) if pulls is None else pulls
    _, reliable = arm_angle(pose, arm)
    # Time every cycle of this arm the same way: from the upper arm when it was seen at every
    # pull, otherwise from the wrist. Mixing the two would add their offset to the rhythm.
    by_upper = len(pulls) > 1 and all(p.mid_upper is not None for p in pulls)
    cycles = []
    for first, second in zip(pulls[:-1], pulls[1:], strict=True):
        # The cycle's boundaries and its duration come from the same event, so that
        # end - start is the duration (to the frame).
        t0, t1 = (first.mid_upper, second.mid_upper) if by_upper else (first.mid, second.mid)
        start, end = round(t0), round(t1)
        duration = float((t1 - t0) / pose.fps)
        # Only the parts an underwater camera can see: the rest of the first pull, and the
        # second one from its reach. Between them the arm is above the water.
        frames = np.concatenate(
            [np.arange(start, first.exit + 1), np.arange(second.start, end + 1)]
        )
        ok = reliable[frames] >= MIN_RELIABLE_CONFIDENCE
        # The longest stretch inside the cycle where the arm was not seen at all.
        unseen = run = 0
        for hidden in reliable[start : end + 1] <= 0:
            run = run + 1 if hidden else 0
            unseen = max(unseen, run)
        reason = kind = ""
        # An unseen stroke only counts if there is room for one: at least the shortest
        # plausible cycle after the first pull and before the second.
        room = CYCLE_SECONDS[0] * pose.fps
        hidden_stroke = any(
            k - first.mid >= room and second.mid - k >= room for k in second.missed_before
        )
        if hidden_stroke:
            reason = "a stroke between these two was not seen clearly enough to count"
            kind = "merged"
        elif unseen > MAX_UNSEEN_SHARE * max(1, end - start):
            reason = (
                f"the arm was not seen for {unseen / pose.fps:.2f} s of this "
                f"{(end - start) / pose.fps:.2f} s stretch: a stroke could be hidden in it"
            )
            kind = "merged"
        elif ok.mean() < MIN_TRUSTED_FRACTION:
            reason = f"only {ok.mean():.0%} of frames have a reliable shoulder and wrist"
            kind = "hidden"
        elif not CYCLE_SECONDS[0] <= duration <= CYCLE_SECONDS[1]:
            reason = f"{duration:.2f} s is outside {CYCLE_SECONDS[0]}-{CYCLE_SECONDS[1]} s"
            kind = "fragment" if duration < CYCLE_SECONDS[0] else "merged"
        cycles.append(
            StrokeCycle(
                arm=arm,
                start=start,
                end=end,
                reach=second.reach,
                duration_s=duration,
                trusted=not reason,
                reason=reason,
                pull_start=second.start,
                pull_end=second.exit,
                kind=kind,
                timing="upper_arm" if by_upper else "wrist",
            )
        )
    return cycles


def main_stretch(pose: CleanPose) -> tuple[int, int] | None:
    """First and last frame of the longest stretch where the swimmer is seen, bridging
    gaps up to `SECTION_MAX_GAP_S`. Skips stray detections before or after the swim, like
    a camera starting above water."""
    seen = np.nonzero(np.isfinite(pose.body_axis()).all(axis=1))[0]
    if len(seen) == 0:
        return None
    max_gap = max(1, round(SECTION_MAX_GAP_S * pose.fps))
    breaks = np.nonzero(np.diff(seen) > max_gap)[0]
    starts = np.concatenate([[0], breaks + 1])
    ends = np.concatenate([breaks, [len(seen) - 1]])
    longest = int(np.argmax(seen[ends] - seen[starts]))
    return int(seen[starts[longest]]), int(seen[ends[longest]])


def find_sections(pose: CleanPose, n: int = len(SECTION_NAMES)) -> list[Section]:
    """Split the main stretch of swimming into equal-time thirds."""
    stretch = main_stretch(pose)
    if stretch is None:
        return []
    edges = np.linspace(stretch[0], stretch[1] + 1, n + 1).round().astype(int)
    return [Section(SECTION_NAMES[i], int(edges[i]), int(edges[i + 1] - 1)) for i in range(n)]


def flag_odd_durations(cycles: list[StrokeCycle]) -> None:
    """Mark cycles far from the clip's typical length as unsure.

    Short reliable fragments happen when only part of a stroke is visible (filmed from
    above, the pull is under the water and the model sees mostly the recovery). Both arms
    share one rhythm, so the typical length is the median over all cycles of both arms.
    """
    if len(cycles) < MIN_CYCLES_FOR_TYPICAL:
        return
    typical = float(np.median([c.duration_s for c in cycles]))
    for c in cycles:
        ratio = c.duration_s / typical
        if c.trusted and not TYPICAL_RATIO[0] <= ratio <= TYPICAL_RATIO[1]:
            c.trusted = False
            c.reason = f"{c.duration_s:.2f} s is far from this clip's typical {typical:.2f} s"
            c.kind = "merged" if ratio > 1 else "fragment"


def _partial_cycles(pose: CleanPose, pulls: dict[str, list[Pull]]) -> list[PartialCycle]:
    """The stretch before an arm's first mid-pull and after its last: part of a cycle that
    started before the clip or ends after it. Never counted."""
    stretch = main_stretch(pose)
    if stretch is None:
        return []
    out = []
    min_frames = max(2, round(0.2 * pose.fps))
    for arm, items in pulls.items():
        if not items:
            continue
        first, last = round(items[0].mid), round(items[-1].mid)
        if first - stretch[0] >= min_frames:
            out.append(PartialCycle(arm, stretch[0], first))
        if stretch[1] - last >= min_frames:
            out.append(PartialCycle(arm, last, stretch[1]))
    return out


def analyze_strokes(pose: CleanPose) -> StrokeAnalysis:
    sections = find_sections(pose)
    cycles, rates = [], {}
    pulls = {arm: find_pulls(pose, arm) for arm in ARMS}
    for arm in ARMS:
        cycles += find_cycles(pose, arm, pulls[arm])
    flag_odd_durations(cycles)
    for arm in ARMS:
        durations = [c.duration_s for c in cycles if c.arm == arm and c.trusted]
        rates[arm] = 60.0 / float(np.median(durations)) if durations else float("nan")
    for c in cycles:
        middle = (c.start + c.end) // 2
        c.section = next((s.name for s in sections if s.start <= middle <= s.end), "")
    cycles.sort(key=lambda c: c.start)
    return StrokeAnalysis(
        cycles=cycles,
        sections=sections,
        rate_per_min=rates,
        pulls=pulls,
        partial=_partial_cycles(pose, pulls),
    )
