"""Biomechanics metrics, each with its own evidence and reliability.

Input: the cleaned pose, the stroke cycles and pulls, which arm faces the camera, and the
direction of travel. Output: a list of `Metric` (measured, limited or unavailable with the
reason). Deterministic; no model, no LLM, no judgement of good or bad technique.

Every definition, criterion and limit is written out in docs/BIOMECHANICS_METRICS.md. The
thresholds are engineering baselines, not validated cut-offs.
"""

from collections.abc import Callable

import numpy as np

from aquatrack.analysis.metrics.cycles import (
    ARMS,
    StrokeAnalysis,
    StrokeCycle,
    arm_angle,
    pull_angle,
)
from aquatrack.analysis.metrics.technique import (
    _agrees_with_neighbours,
    _Geometry,
    joint_angle,
    measure_technique,
)
from aquatrack.analysis.usability import ArmUse, ViewCheck, unusable_points
from aquatrack.contracts import (
    CameraSide,
    Metric,
    MetricKind,
    MetricSample,
    MetricStatus,
    SessionInfo,
)

MIN_CYCLES = 3  # fewer cycles than this is "limited"
MIN_CYCLES_RHYTHM = 4  # a spread needs one more
MIN_COVERAGE_PCT = 70.0  # of the frames in the cycles used
MIN_CYCLE_COVERAGE = 0.5  # a cycle gives a value only with this share of its frames usable
MIN_SECTION_CYCLES = 3  # per third of the swim, to compare start / middle / end
MAX_EDGE_CYCLES = 1.2  # a part-cycle at the clip edge longer than this many cycles hides a pull
# A geometric value that climbs or falls steadily through the clip is more often the camera's
# viewing angle changing (a pan as the swimmer passes) than the swimmer changing.
DRIFT_MIN_SAMPLES = 4
ELBOW_PHASE_DEG = (45, 135)  # arm angle from straight ahead: the part under the shoulder
CATCH_UPPER_ARM_DEG = 45.0  # the catch: upper arm this far below the direction of travel
# (30 degrees often comes before the pull is followed at all, above all in sprints)
MAX_CATCH_GAP = 2  # frames between the supported frames either side of that moment
MIN_ELBOW_FRAMES = 3
DRIFT_MIN_CORRELATION = 0.8
MAX_HORIZON_SPREAD_DEG = 6.0  # pool-line direction wandering more than this is not trusted
HEAD = [0, 1, 2, 3, 4]  # nose, eyes, ears
TRUNK = [5, 6, 11, 12]
ANKLES = [15, 16]

PROJECTION = (
    "Measured in the picture, from one side camera: movement toward or away from the camera "
    "is not seen."
)
SMALL_SAMPLE = "Checked on two real clips of one swimmer; not scientifically validated."

# key: (label, group, kind, unit, description, limitations)
DEFS: dict[str, tuple[str, str, MetricKind, str, str, list[str]]] = {
    "stroke_rate": (
        "Stroke rate",
        "timing",
        MetricKind.TEMPORAL,
        "cycles/min",
        "Full arm cycles per minute. One cycle is one full turn of one arm, so both arms "
        "together make two strokes per cycle.",
        ["From the cycles that could be followed; a short clip covers only a few."],
    ),
    "cycle_duration": (
        "Time per stroke cycle",
        "timing",
        MetricKind.TEMPORAL,
        "s",
        "Median time from one mid-pull of an arm to its next.",
        ["Timed to the nearest video frame."],
    ),
    "cycle_count": (
        "Stroke cycles counted",
        "timing",
        MetricKind.TEMPORAL,
        "cycles",
        "Whole cycles of one arm between its first and last mid-pull in the clip. Each cycle "
        "is two arm strokes (one per arm).",
        [
            "Not the number of strokes in a length: the clip's first and last part-cycles "
            "are left out.",
        ],
    ),
    "rhythm_variation": (
        "Rhythm variation",
        "consistency",
        MetricKind.TEMPORAL,
        "%",
        "How much the cycle time changes from cycle to cycle (standard deviation as a share "
        "of the mean). Lower means a steadier rhythm.",
        [
            "With few cycles one odd cycle moves this a lot.",
            "It does not say why the rhythm changed (a breath, a turn, the camera).",
        ],
    ),
    "body_line_angle": (
        "Body line angle",
        "body",
        MetricKind.GEOMETRIC,
        "deg",
        "Angle of the shoulder-hip-ankle line against the direction of travel. 0 is level; "
        "positive means the feet are lower than the shoulders.",
        [PROJECTION, "Depends on knowing which way is level in the picture.", SMALL_SAMPLE],
    ),
    "leg_line_angle": (
        "Legs against the trunk line",
        "body",
        MetricKind.GEOMETRIC,
        "deg",
        "Angle of the hip-to-ankle line against the trunk line carried on past the hips. "
        "0 is one straight line; positive means the legs sit below it.",
        [
            PROJECTION,
            "The kick moves the ankles; the median over each cycle is used.",
            SMALL_SAMPLE,
        ],
    ),
    "head_height": (
        "Head against the trunk line",
        "body",
        MetricKind.GEOMETRIC,
        "trunk lengths",
        "How far the middle of the face sits above (positive) or below the trunk line carried "
        "forward past the shoulders. 0 is in line with the trunk.",
        [
            PROJECTION,
            "The face points stand in for the head; the trunk line shifts a little as the "
            "shoulders roll.",
            "Includes the moments of breathing.",
            SMALL_SAMPLE,
        ],
    ),
    "pull_depth": (
        "Pull depth",
        "arm",
        MetricKind.GEOMETRIC,
        "trunk lengths",
        "Deepest point of the wrist below the shoulder during the underwater pull, for the "
        "arm nearer the camera.",
        [
            PROJECTION,
            "Only the arm nearer the camera; the other arm is not measured.",
            SMALL_SAMPLE,
        ],
    ),
    "elbow_angle_min": (
        "Elbow bend in the pull (2D)",
        "arm",
        MetricKind.PROXY,
        "deg",
        "Smallest elbow angle seen in the picture while the arm passes under the shoulder, "
        "for the arm nearer the camera (180 is a straight arm).",
        [
            "A picture angle, not the true joint angle: an arm bent toward or away from the "
            "camera looks straighter or more bent than it is.",
            "Only the arm nearer the camera, and not the end of the push: near the hip and the "
            "surface the wrist is often placed wrongly.",
            SMALL_SAMPLE,
        ],
    ),
    "catch_forearm_angle": (
        "Forearm angle at the catch (2D)",
        "arm",
        MetricKind.PROXY,
        "deg",
        "How far the forearm still points forward, away from straight down, at the moment the "
        "upper arm has dropped 45 degrees below the direction of travel, for the arm nearer "
        "the camera. 0 is a forearm pointing straight down.",
        [
            "A picture angle: a forearm turned toward or away from the camera looks more or "
            "less vertical than it is.",
            "Only the arm nearer the camera, and only pulls whose start was followed.",
            "Checked against human labels on SWIM-360 (370 frames, 9 freestyle swims): "
            "forearm direction within 2.4 degrees typically, 6.7 degrees in 9 of 10 frames, "
            "for a visible arm. Not checked as a whole metric on full clips.",
        ],
    ),
    "pull_path_variation": (
        "Pull path variation",
        "consistency",
        MetricKind.GEOMETRIC,
        "trunk lengths",
        "How far each pull's wrist path (relative to the shoulder) is from the average path "
        "of the same arm. Lower means the pulls repeat more closely.",
        [
            PROJECTION,
            "Pose noise adds to it, so it never reaches 0.",
            "Only the arm nearer the camera.",
            SMALL_SAMPLE,
        ],
    ),
    "cycle_time_change": (
        "Cycle time, start to end",
        "consistency",
        MetricKind.TEMPORAL,
        "s",
        "Median cycle time in the last third of the swim minus the first third.",
        ["A change in a short clip is not evidence of fatigue."],
    ),
}

# Asked for by the product, not measurable from one underwater side view (or not checked).
NOT_MEASURED: list[tuple[str, str, str]] = [
    (
        "left_right_balance",
        "Left-right balance",
        "Needs both arms followed through whole pulls. From the side the far arm is hidden "
        "behind the body for part of every pull.",
    ),
    (
        "arm_coordination",
        "Arm coordination",
        "Needs the start and end of both arms' pulls. The far arm's are hidden from a side view.",
    ),
    (
        "kick_rhythm",
        "Kick rhythm",
        "Kick beats are computed but have not been checked against video yet, and the far leg "
        "is often hidden.",
    ),
    (
        "breathing_timing",
        "Breathing timing",
        "The head turn is not seen reliably from an underwater side view; the experimental "
        "detector has not been checked against video.",
    ),
    (
        "body_rotation",
        "Body rotation",
        "Rotation around the body's long axis cannot be measured from one side camera. It "
        "needs a front or overhead view.",
    ),
    (
        "propulsion",
        "Propulsion and efficiency",
        "Force and efficiency cannot be measured from video of joint positions alone.",
    ),
]


def _round(value: float, unit: str) -> float:
    return round(float(value), 1 if unit in ("deg", "cycles/min", "%") else 2)


def _metric(key: str, status: MetricStatus, **fields) -> Metric:
    label, group, kind, unit, description, limitations = DEFS[key]
    return Metric(
        key=key,
        label=label,
        group=group,
        kind=kind,
        unit=unit,
        description=description,
        status=status,
        limitations=limitations,
        **fields,
    )


def _unavailable(key: str, reason: str) -> Metric:
    return _metric(key, MetricStatus.UNAVAILABLE, reason=reason)


def _from_samples(
    key: str,
    samples: list[MetricSample],
    coverage_pct: float | None,
    basis: str,
    caps: list[str],
    min_cycles: int = MIN_CYCLES,
    side: str | None = None,
    value: float | None = None,
    none_reason: str = "No stroke cycle gave a usable value.",
) -> Metric:
    """Median and spread over per-cycle samples, graded by this metric's own evidence."""
    if not samples:
        return _unavailable(key, none_reason)
    unit = DEFS[key][3]
    values = np.array([s.value for s in samples])
    reasons = list(caps)
    if DEFS[key][2] is not MetricKind.TEMPORAL and drifts(samples):
        reasons.append(
            "The value climbs or falls steadily through the clip. That is more often the "
            "camera's viewing angle changing than the swimmer, so the middle value is not a "
            "fair summary."
        )
    if len(samples) < min_cycles:
        reasons.append(
            f"Only {len(samples)} stroke cycle{'s' if len(samples) != 1 else ''} "
            f"(at least {min_cycles} for a reliable value)."
        )
    if coverage_pct is not None and coverage_pct < MIN_COVERAGE_PCT:
        reasons.append(
            f"The joints it needs were usable in {coverage_pct:.0f}% of the frames "
            f"(at least {MIN_COVERAGE_PCT:.0f}%)."
        )
    return _metric(
        key,
        MetricStatus.LIMITED if reasons else MetricStatus.RELIABLE,
        value=_round(np.median(values) if value is None else value, unit),
        low=_round(np.percentile(values, 25), unit),
        high=_round(np.percentile(values, 75), unit),
        n_cycles=len(samples),
        coverage_pct=None if coverage_pct is None else round(coverage_pct, 1),
        side=side,
        samples=samples,
        basis=basis,
        reason=" ".join(reasons),
    )


def drifts(samples: list[MetricSample]) -> bool:
    """Do the per-cycle values run steadily in one direction through the clip?"""
    if len(samples) < DRIFT_MIN_SAMPLES:
        return False
    t = np.array([s.t_s for s in samples])
    v = np.array([s.value for s in samples])
    if np.ptp(v) == 0 or np.ptp(t) == 0:
        return False
    rank = lambda x: np.argsort(np.argsort(x)).astype(float)  # noqa: E731
    return bool(abs(np.corrcoef(rank(t), rank(v))[0, 1]) >= DRIFT_MIN_CORRELATION)


def _per_cycle(
    series: np.ndarray,
    ok: np.ndarray,
    cycles: list[StrokeCycle],
    seconds: Callable[[int], float],
    unit: str,
) -> tuple[list[MetricSample], float | None]:
    """The median of a per-frame series over each cycle, from usable frames only."""
    samples, used, total = [], 0, 0
    for c in cycles:
        frames = np.arange(c.start, c.end + 1)
        f = frames[ok[frames]]
        used += len(f)
        total += len(frames)
        if len(f) < max(3, MIN_CYCLE_COVERAGE * len(frames)):
            continue
        middle = float(np.median(series[f]))
        shows = int(f[np.argmin(np.abs(series[f] - middle))])
        samples.append(
            MetricSample(
                t_s=seconds(shows),
                value=_round(middle, unit),
                start_s=seconds(c.start),
                end_s=seconds(c.end),
            )
        )
    return samples, (100.0 * used / total if total else None)


def catch_angles(
    g: _Geometry,
    xy: np.ndarray,
    arm: str,
    cycles: list[StrokeCycle],
    supported: np.ndarray,
    seconds: Callable[[int], float],
) -> list[MetricSample]:
    """Forearm angle from straight down at the catch, one value per pull.

    The catch is the moment the upper arm crosses `CATCH_UPPER_ARM_DEG` below the direction
    of travel, between the pull's start and mid-pull. Both frames either side of that moment
    must be supported (the model's own points, inside a followed pull) and at most
    `MAX_CATCH_GAP` frames apart; the value is interpolated between them, since the arm turns
    several degrees per frame. Positive: the hand is still ahead of the elbow.
    """
    shoulder, wrist = ARMS[arm]
    elbow = 7 if arm == "left" else 8
    upper = g.tilt(xy[:, elbow] - xy[:, shoulder])
    forearm = xy[:, wrist] - xy[:, elbow]
    with np.errstate(invalid="ignore"):
        from_down = np.degrees(np.arctan2(g.along(forearm), g.depth(forearm)))
    samples = []
    for c in cycles:
        if c.pull_start is None or c.end is None:
            continue
        # The pull that ends this cycle runs from pull_start to its mid-pull, which is c.end.
        frames = np.arange(c.pull_start, c.end + 1)
        f = frames[supported[frames] & np.isfinite(upper[frames]) & np.isfinite(from_down[frames])]
        if len(f) < 2 or upper[f[0]] >= CATCH_UPPER_ARM_DEG:
            continue  # the start of the pull wasn't followed: the catch can't be placed
        crossed = np.nonzero(upper[f] >= CATCH_UPPER_ARM_DEG)[0]
        if not len(crossed):
            continue
        k1, k0 = int(f[crossed[0]]), int(f[crossed[0] - 1])
        if k1 - k0 > MAX_CATCH_GAP:
            continue
        t = (CATCH_UPPER_ARM_DEG - upper[k0]) / (upper[k1] - upper[k0])
        value = float(from_down[k0] + t * (from_down[k1] - from_down[k0]))
        shows = k1 if t >= 0.5 else k0
        samples.append(
            MetricSample(
                t_s=seconds(shows),
                value=_round(value, "deg"),
                start_s=seconds(c.start),
                end_s=seconds(c.end),
            )
        )
    return samples


def timing_arm(strokes: StrokeAnalysis, side: CameraSide) -> str | None:
    """The arm cycles are timed and counted on: the camera-side arm when it is known and has
    cycles, else the arm with more reliable cycles."""
    counts = {arm: sum(c.trusted and c.arm == arm for c in strokes.cycles) for arm in ARMS}
    if side.arm and counts[side.arm]:
        return side.arm
    best = max(counts, key=counts.get)
    return best if counts[best] else None


def measure(
    pose,
    strokes: StrokeAnalysis,
    side: CameraSide,
    horizon: np.ndarray,
    horizon_source: str,
    session: SessionInfo,
    timestamps_s: np.ndarray,
    use: dict[str, ArmUse],
    view: ViewCheck,
    withhold: str = "",
) -> list[Metric]:
    """All metrics for one clip. `withhold` (a reason) makes every metric unavailable, for
    clips where the swimmer could not be followed well enough to stand behind any number.

    `use` says which arm frames are supported (only those are read for arm metrics) and
    `view` which cycles were filmed too far off side-on (left out of everything measured
    as a position or an angle in the picture; timing is not affected by the view)."""
    if withhold:
        return [_unavailable(key, withhold) for key in DEFS]

    def seconds(i: int) -> float:
        return round(float(timestamps_s[int(i)]), 3)

    caps = []  # reasons that hold every metric at "limited"
    stroke, camera = session.stroke.lower(), session.camera.lower()
    if stroke and stroke != "freestyle":
        caps.append(f"Only checked on freestyle so far, not {stroke}.")
    if camera and not camera.startswith("underwater"):
        caps.append(f"Only checked on underwater side views, not {camera}.")

    arm = timing_arm(strokes, side)
    cycles = [c for c in strokes.cycles if c.arm == arm and c.trusted] if arm else []
    which = f"{arm} arm" + (", nearer the camera" if side.arm == arm else "") if arm else "no arm"
    basis = f"{len(cycles)} reliable cycle{'s' if len(cycles) != 1 else ''} of the {which}"
    timing_basis = basis
    no_cycles = "No complete stroke cycle could be followed in this clip."
    out: list[Metric] = []

    # ---- timing
    timing = [
        MetricSample(
            t_s=seconds(c.start),
            value=round(c.duration_s, 2),
            start_s=seconds(c.start),
            end_s=seconds(c.end),
        )
        for c in cycles
    ]
    median_s = float(np.median([c.duration_s for c in cycles])) if cycles else float("nan")
    rate = _from_samples("stroke_rate", timing, None, basis, caps, none_reason=no_cycles)
    if cycles:
        per_cycle = 60.0 / np.array([c.duration_s for c in cycles])
        rate.value = _round(60.0 / median_s, "cycles/min")
        rate.low = _round(np.percentile(per_cycle, 25), "cycles/min")
        rate.high = _round(np.percentile(per_cycle, 75), "cycles/min")
        rate.samples = [
            s.model_copy(update={"value": _round(60.0 / s.value, "cycles/min")}) for s in timing
        ]
    out.append(rate)
    out.append(_from_samples("cycle_duration", timing, None, basis, caps, none_reason=no_cycles))

    # A count is only a count when every cycle of that arm was followed. With a merged or
    # hidden one in between, the reliable cycles still give a rate, but their number is not
    # how many there were.
    every = [c for c in strokes.cycles if c.arm == arm] if arm else []
    unclear = sum(not c.trusted for c in every)
    edges = [(timestamps_s[p.end] - timestamps_s[p.start]) for p in strokes.partial if p.arm == arm]
    if not cycles:
        out.append(_unavailable("cycle_count", no_cycles))
    elif unclear:
        out.append(
            _unavailable(
                "cycle_count",
                f"{unclear} of the {len(every)} {arm}-arm cycles could not be followed clearly, "
                "so a count would be wrong. The stroke rate uses the clear ones.",
            )
        )
    elif edges and max(edges) > MAX_EDGE_CYCLES * median_s:
        out.append(
            _unavailable(
                "cycle_count",
                f"There are {max(edges):.1f} s of swimming before the first or after the last "
                f"{arm}-arm pull that was followed, longer than one cycle ({median_s:.1f} s): "
                "a pull was missed there, so a count would be too low.",
            )
        )
    else:
        count = _from_samples("cycle_count", timing, None, basis, caps, min_cycles=1)
        count.value, count.low, count.high = float(len(cycles)), None, None
        count.samples = []  # the cycles themselves are listed under cycle_duration
        out.append(count)

    durations = np.array([c.duration_s for c in cycles])
    if len(durations) >= MIN_CYCLES:
        cv = 100.0 * float(np.std(durations, ddof=1) / np.mean(durations))
        rhythm = _from_samples(
            "rhythm_variation", timing, None, basis, caps, MIN_CYCLES_RHYTHM, value=cv
        )
        rhythm.low = rhythm.high = None
        rhythm.samples = []  # the cycle times themselves are listed under cycle_duration
        frame_pct = 100.0 / (pose.fps * median_s)
        rhythm.limitations = [
            *rhythm.limitations,
            f"One video frame is {frame_pct:.1f}% of a cycle here, so differences of that size "
            "are below what can be timed.",
        ]
        out.append(rhythm)
    else:
        out.append(
            _unavailable(
                "rhythm_variation",
                f"Needs at least {MIN_CYCLES} reliable cycles of one arm; this clip has "
                f"{len(durations)}.",
            )
        )

    # ---- body position (any arm's cycles serve as time windows)
    # Positions and angles in the picture only mean something seen side-on.
    timing_cycles = cycles
    cycles = [c for c in timing_cycles if c.start not in view.unsuitable]
    left_out = len(timing_cycles) - len(cycles)
    if left_out:
        basis = (
            f"{len(cycles)} of the {len(timing_cycles)} reliable cycles of the {which}; "
            f"{left_out} left out because the swimmer was seen at an angle"
        )
        no_cycles = "Every reliable stroke cycle was filmed too far off side-on."
    unusable = unusable_points(pose, use)
    g = _Geometry(pose, horizon, unusable)
    xy = pose.xy
    shoulders, hips = pose.shoulder_center(), pose.hip_center()
    axis = pose.body_axis()
    up = np.stack(
        [axis[:, 1], -axis[:, 0]], axis=1
    )  # perpendicular to the trunk, toward the surface
    ok_trunk, _ = g.ok(TRUNK)

    report = measure_technique(
        pose, strokes, horizon, horizon_source, near_side=side.arm, unusable=unusable
    )
    starts = {c.start: c for c in cycles}

    def from_report(name: str, want_side: str | None) -> list[MetricSample]:
        """Per-cycle values of an existing technique measure, for the cycles in `starts`."""
        unit = report.measures[name].unit
        samples, seen = [], set()
        for v in report.measures[name].values:
            c = starts.get(v.cycle_start)
            if c is None or v.side != want_side or v.frame is None or c.start in seen:
                continue
            seen.add(c.start)  # the other arm's cycle can start on the same frame
            samples.append(
                MetricSample(
                    t_s=seconds(v.frame),
                    value=_round(v.value, "deg" if unit == "deg" else "trunk"),
                    start_s=seconds(c.start),
                    end_s=seconds(c.end),
                )
            )
        return samples

    ok_ankle = g.ok([ANKLES[0]])[0] | g.ok([ANKLES[1]])[0]
    line_caps = list(caps)
    if horizon_source == "frame horizontal":
        line_caps.append(
            "The direction of travel could not be found, so the picture's own horizontal is "
            "used: a tilted camera shifts this angle."
        )
    elif np.ptp(np.degrees(horizon)) > MAX_HORIZON_SPREAD_DEG:
        line_caps.append(
            f"The level reference ({horizon_source}) wandered by "
            f"{np.ptp(np.degrees(horizon)):.0f} degrees through the clip."
        )
    geometric_from = len(out)
    _, line_cov = _per_cycle(np.zeros(len(pose)), ok_trunk & ok_ankle, cycles, seconds, "deg")
    out.append(
        _from_samples(
            "body_line_angle",
            from_report("body_line_angle", None),
            line_cov,
            f"{basis}; level taken from the {horizon_source}",
            line_caps,
            none_reason=no_cycles,
        )
    )

    with np.errstate(invalid="ignore"):
        both = g.ok([ANKLES[0]])[0] & g.ok([ANKLES[1]])[0]
        ankle = np.where(
            both[:, None],
            (xy[:, 15] + xy[:, 16]) / 2,
            np.where(g.ok([ANKLES[0]])[0][:, None], xy[:, 15], xy[:, 16]),
        )
        legs = hips - ankle  # pointing the same way as the trunk when in line
        leg_angle = np.degrees(
            np.arctan2(-np.einsum("fd,fd->f", legs, up), np.einsum("fd,fd->f", legs, axis))
        )
    ok_legs = ok_trunk & ok_ankle & np.isfinite(leg_angle)
    samples, cov = _per_cycle(-leg_angle, ok_legs, cycles, seconds, "deg")
    out.append(_from_samples("leg_line_angle", samples, cov, basis, caps, none_reason=no_cycles))

    face, ok_face = g.center(HEAD, min_fraction=0.6)
    with np.errstate(invalid="ignore"):
        head = np.einsum("fd,fd->f", face - shoulders, up) / pose.trunk
    ok_head = ok_face & ok_trunk & np.isfinite(head)
    samples, cov = _per_cycle(head, ok_head, cycles, seconds, "trunk")
    out.append(_from_samples("head_height", samples, cov, basis, caps, none_reason=no_cycles))

    # ---- arm geometry: only the arm nearer the camera, only inside its underwater pulls
    arm_keys = ("pull_depth", "elbow_angle_min", "catch_forearm_angle", "pull_path_variation")
    if side.arm is None:
        why = side.reason or "It is not clear which arm is nearer the camera."
        out += [
            _unavailable(k, f"{why} Arm shape is only read from the nearer arm.") for k in arm_keys
        ]
    else:
        every_near = [c for c in strokes.cycles if c.arm == side.arm and c.trusted]
        near = [c for c in every_near if c.start not in view.unsuitable]
        starts = {c.start: c for c in near}
        # Coverage: frames of those pulls where the arm is supported (model points for
        # shoulder, elbow and wrist, believable segment lengths). Frames where the wrist is
        # pulled up against the elbow as the hand leaves the water lower it, as they should.
        supported = use[side.arm].followed
        used = total = collapsed = 0
        for c in near:
            pull = np.arange(c.pull_start or c.reach, (c.pull_end or c.end) + 1)
            used += int(supported[pull].sum())
            collapsed += int(use[side.arm].collapsed[pull].sum())
            total += len(pull)
        arm_cov = 100.0 * used / total if total else None
        arm_basis = (
            f"{len(near)} underwater pull{'s' if len(near) != 1 else ''} of the {side.arm} arm "
            "(nearer the camera), from where it leaves the front to the last frame it was followed"
        )
        if collapsed:
            arm_basis += (
                f"; {collapsed} frame{'s' if collapsed != 1 else ''} left out where the "
                "forearm or upper arm was drawn impossibly short"
            )
        if len(every_near) > len(near):
            arm_basis += (
                f"; {len(every_near) - len(near)} pulls left out because the swimmer was "
                "seen at an angle"
            )
        none = (
            f"No underwater pull of the {side.arm} arm could be followed side-on."
            if every_near
            else f"No underwater pull of the {side.arm} arm could be followed."
        )
        out.append(
            _from_samples(
                "pull_depth",
                from_report("pull_depth", side.arm),
                arm_cov,
                arm_basis,
                caps,
                side=side.arm,
                none_reason=none,
            )
        )
        # Elbow: only while the arm passes under the shoulder. Past ELBOW_PHASE_DEG[1] the hand
        # nears the hip and the surface, and on real clips the model then pulls the wrist up
        # against the elbow, which reads as a sharp bend that is not there.
        shoulder, wrist = ARMS[side.arm]
        elbow = 7 if side.arm == "left" else 8
        angle, _ = arm_angle(pose, side.arm)
        angle = np.degrees(pull_angle(angle))
        bend = joint_angle(xy[:, shoulder], xy[:, elbow], xy[:, wrist])
        elbow_samples = []
        for c in near:
            pull = np.arange(c.pull_start or c.reach, (c.pull_end or c.end) + 1)
            with np.errstate(invalid="ignore"):
                under = (angle[pull] >= ELBOW_PHASE_DEG[0]) & (angle[pull] <= ELBOW_PHASE_DEG[1])
            f = pull[supported[pull] & under]
            f = f[_agrees_with_neighbours(f, bend[f])]
            if len(f) >= MIN_ELBOW_FRAMES:
                k = int(f[np.argmin(bend[f])])
                elbow_samples.append(
                    MetricSample(
                        t_s=seconds(k),
                        value=_round(bend[k], "deg"),
                        start_s=seconds(c.start),
                        end_s=seconds(c.end),
                    )
                )
        out.append(
            _from_samples(
                "elbow_angle_min",
                elbow_samples,
                arm_cov,
                arm_basis,
                [*caps, "A picture angle from one camera, not the true joint angle."],
                side=side.arm,
                none_reason=none,
            )
        )
        catch_samples = catch_angles(g, xy, side.arm, near, supported, seconds)
        out.append(
            _from_samples(
                "catch_forearm_angle",
                catch_samples,
                arm_cov,
                arm_basis,
                [*caps, "A picture angle from one camera, not the true joint angle."],
                side=side.arm,
                none_reason=f"No pull of the {side.arm} arm was followed through the catch "
                "(the moment the upper arm drops 45 degrees).",
            )
        )
        out.append(
            _from_samples(
                "pull_path_variation",
                from_report("pull_shape_spread", side.arm),
                arm_cov,
                arm_basis,
                caps,
                side=side.arm,
                none_reason=f"Needs at least 2 pulls of the {side.arm} arm followed most of "
                "the way.",
            )
        )

    for metric in out[geometric_from:]:
        metric.excluded_cycles = left_out
    cycles, basis = timing_cycles, timing_basis

    # ---- start / middle / end
    by_section = {
        name: [c for c in cycles if c.section == name] for name in ("start", "middle", "end")
    }
    if all(len(v) >= MIN_SECTION_CYCLES for v in by_section.values()):
        medians = {k: float(np.median([c.duration_s for c in v])) for k, v in by_section.items()}
        change = _from_samples(
            "cycle_time_change",
            [
                MetricSample(
                    t_s=seconds(v[0].start),
                    value=round(medians[k], 2),
                    start_s=seconds(v[0].start),
                    end_s=seconds(v[-1].end),
                    label=k,
                )
                for k, v in by_section.items()
            ],
            None,
            basis + ", split into thirds of the swim",
            caps,
            value=medians["end"] - medians["start"],
        )
        change.low = change.high = None
        change.n_cycles = len(cycles)
        spread = float(np.std(durations, ddof=1))
        if abs(medians["end"] - medians["start"]) <= spread:
            change.status = MetricStatus.LIMITED
            change.reason = (
                change.reason + f" The change is within the normal cycle-to-cycle variation "
                f"of this clip ({spread:.2f} s): no clear change."
            ).strip()
        out.append(change)
    else:
        have = ", ".join(f"{len(v)} in the {k}" for k, v in by_section.items())
        out.append(
            _unavailable(
                "cycle_time_change",
                f"The clip is too short to compare its start, middle and end: each third needs "
                f"at least {MIN_SECTION_CYCLES} reliable cycles ({have}).",
            )
        )
    return out
