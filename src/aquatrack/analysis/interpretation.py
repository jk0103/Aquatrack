"""Interpretation: what the measurements of one swim support saying, and no more.

Input: a stored `AnalysisResult` (any schema version), the swimmer's own context, and their
earlier analyses. Output: an `Interpretation`. No pose data, no model, no LLM: it can be run
again on saved results at any time.

Three levels are kept apart:

  observation       a statement about the measurements themselves
  issue candidate   a pattern with enough evidence to be worth the swimmer's attention
  priority          an issue candidate that is also backed by repetition across swims or
                    by a goal the swimmer set

A measurement is never a problem just because of its value. There is no ideal angle, no
score and no comparison with other swimmers anywhere in this module: every rule works on
the swimmer's own cycles and their own earlier swims. Rules that would need an outside
reference (which direction of a body angle is "better", what stroke rate suits a distance)
are listed as `pending_validation` and do nothing.

Every rule, threshold and limit is written out in docs/INTERPRETATION_RULES.md.
"""
# ruff: noqa: E501  (the sentences shown to the swimmer are kept whole, one per line)

from dataclasses import dataclass, field

import numpy as np

from aquatrack.contracts import (
    AnalysisResult,
    ContextUsed,
    Finding,
    FindingEvidence,
    Interpretation,
    Metric,
    MetricChange,
    MetricStatus,
    PriorityCandidate,
    PriorityFactor,
    QualityGrade,
    RuleStatus,
    SessionComparison,
    Undetermined,
)

RULES_VERSION = "2026.11-1"

# ---- which metrics may be used for what (availability is not interpretive validity)
# May trigger an issue candidate, when they passed their own Phase 2 checks.
ISSUE_ELIGIBLE = {"cycle_duration", "rhythm_variation"}
# May be described and compared with the swimmer's own earlier swims. No rule turns them
# into an issue: which direction is "better" needs a verified outside reference.
DESCRIBE_AND_COMPARE = {
    "stroke_rate",
    "cycle_duration",
    "rhythm_variation",
    "body_line_angle",
    "leg_line_angle",
    "head_height",
}
GEOMETRIC = {"body_line_angle", "leg_line_angle", "head_height"}
# Shown as context only. Phase 2 left open problems with them (wrist placement at the end of
# the push, few supported frames), so they never trigger anything and are not compared.
CONTEXT_ONLY = {"pull_depth", "elbow_angle_min", "pull_path_variation"}

# ---- measurement resolution: differences below these cannot be told from noise
RESOLUTION = {"body_line_angle": 2.0, "leg_line_angle": 2.0, "head_height": 0.05}  # deg, trunk
TIMING_FRAMES = 2  # a cycle time is uncertain by about one frame at each end

# ---- rule thresholds (engineering baselines, not norms)
MIN_CYCLES_RHYTHM_ISSUE = 6  # cycles of one arm, to speak of a repeated pattern
ODD_CYCLE_FRAMES = 3  # a cycle is "off the rhythm" if further than this from the median ...
ODD_CYCLE_SHARE = 0.10  # ... and further than this share of it
MIN_ODD_CYCLES = 3
MIN_ODD_SHARE = 0.25
MAX_PACE_DIFFERENCE = 0.20  # stroke rates further apart are a different effort, not a change
MAX_PRIORITIES = 3

# Goal keys as stored on the profile (frontend/app/lib/profile.ts, firestore.rules).
GOALS = {
    "stroke_consistency": "stroke consistency",
    "body_alignment": "body alignment",
    "arm_technique": "arm technique",
    "speed": "swimming speed",
    "endurance": "endurance",
    "breathing": "breathing",
    "overall_freestyle": "overall freestyle technique",
}

NO_NORM = (
    "No comparison with other swimmers or with an ideal value is made: none has been "
    "verified for this measurement."
)


@dataclass
class SwimmerContext:
    """What the swimmer told us. Anything missing stays missing."""

    swim_level: str | None = None
    pbs: list[dict] = field(default_factory=list)  # {event, pool, seconds}
    goals: list[str] = field(default_factory=list)  # keys of GOALS, from the profile
    primary_goal: str | None = None


@dataclass
class PriorSession:
    video_id: str
    result: AnalysisResult
    analysis_id: str = ""
    recorded_at: str = ""
    synthetic: bool = False


@dataclass
class Rule:
    """An issue rule, documented where it is defined."""

    rule_id: str
    title: str
    metric_keys: tuple[str, ...]
    requires: str  # evidence needed before it can trigger
    logic: str
    suppressed_when: str
    goal_keys: tuple[str, ...] = ()
    active: bool = True
    needs_reference: str = ""  # for rules waiting on outside evidence


RULES = [
    Rule(
        "timing.uneven_rhythm",
        "Several stroke cycles were off the swimmer's own rhythm",
        ("cycle_duration", "rhythm_variation"),
        f"cycle_duration and rhythm_variation both passed their checks; at least "
        f"{MIN_CYCLES_RHYTHM_ISSUE} reliable cycles of one arm; a steady camera view",
        f"A cycle is off the rhythm when its time differs from the clip's median by more than "
        f"{ODD_CYCLE_FRAMES} video frames and by more than {ODD_CYCLE_SHARE:.0%}. Triggers when "
        f"at least {MIN_ODD_CYCLES} cycles and {MIN_ODD_SHARE:.0%} of the cycles are.",
        "the camera view changed during the clip, a metric is limited or unavailable, or "
        "there are too few cycles",
        goal_keys=("stroke_consistency", "overall_freestyle"),
    ),
    Rule(
        "history.rhythm_less_steady",
        "Stroke rhythm less steady than in the swimmer's earlier comparable swim",
        ("rhythm_variation",),
        "rhythm_variation passed its checks in this swim and in at least one compatible "
        "earlier swim",
        "Triggers when rhythm variation is higher than in the most recent compatible swim by "
        "more than twice the combined sampling error of the two values plus the timing "
        "resolution.",
        "there is no compatible earlier swim, or the difference is within noise",
        goal_keys=("stroke_consistency", "overall_freestyle"),
    ),
    Rule(
        "pending.body_line_direction",
        "Body line or leg line judged as better or worse",
        ("body_line_angle", "leg_line_angle"),
        "",
        "",
        "",
        goal_keys=("body_alignment",),
        active=False,
        needs_reference="a verified source for how body and leg line relate to drag or speed "
        "for swimmers of this level, and a check that the picture angle measures it",
    ),
    Rule(
        "pending.head_position",
        "Head position judged as better or worse",
        ("head_height",),
        "",
        "",
        "",
        goal_keys=("body_alignment",),
        active=False,
        needs_reference="a verified source on head position in freestyle, and a head measure "
        "that separates lifting from turning to breathe",
    ),
    Rule(
        "pending.stroke_rate_for_distance",
        "Stroke rate judged against the distance or the swimmer's level",
        ("stroke_rate",),
        "",
        "",
        "",
        goal_keys=("speed",),
        active=False,
        needs_reference="swim speed or distance per stroke for the clip (not measured) and "
        "verified reference ranges for the swimmer's level and event",
    ),
    Rule(
        "pending.arm_pull",
        "Elbow bend, pull depth or pull path judged",
        ("elbow_angle_min", "pull_depth", "pull_path_variation"),
        "",
        "",
        "",
        goal_keys=("arm_technique",),
        active=False,
        needs_reference="arm points that can be trusted through the whole pull (Phase 2 left "
        "wrist placement at the end of the push unresolved) and a second camera view",
    ),
]
RULE = {r.rule_id: r for r in RULES}


# ---------- helpers ----------


def _metric(result: AnalysisResult, key: str) -> Metric | None:
    return next((m for m in result.metrics if m.key == key), None)


def _passed(m: Metric | None) -> bool:
    return m is not None and m.status is MetricStatus.RELIABLE and m.value is not None


def _evidence(m: Metric, note: str = "") -> FindingEvidence:
    return FindingEvidence(
        metric_key=m.key,
        label=m.label,
        value=m.value,
        unit=m.unit,
        low=m.low,
        high=m.high,
        n_cycles=m.n_cycles,
        status=m.status.value,
        samples=m.samples,
        note=note,
    )


def _fps(result: AnalysisResult) -> float:
    return float(result.video.fps) if result.video.fps else 25.0


def _view_changing(result: AnalysisResult) -> bool:
    view = result.coverage.view if result.coverage else None
    return view is not None and view.status == "changing"


def _num(value: float, unit: str) -> str:
    digits = 1 if unit in ("deg", "cycles/min", "%") else 2
    text = f"{value:.{digits}f}"
    if float(text) == 0:
        text = f"{0:.{digits}f}"
    return f"{text}{'°' if unit == 'deg' else ' ' + unit if unit else ''}"


# ---------- context ----------

_EVENT_STROKE = {
    "freestyle": "Free",
    "backstroke": "Back",
    "breaststroke": "Breast",
    "butterfly": "Fly",
}


def _context(result: AnalysisResult, context: SwimmerContext | None) -> ContextUsed:
    used = ContextUsed()
    if context is None:
        used.notes.append("No swimmer profile was available.")
        return used
    used.swim_level = context.swim_level
    used.goals = [g for g in context.goals if g in GOALS]
    used.primary_goal = context.primary_goal if context.primary_goal in used.goals else None
    stroke = _EVENT_STROKE.get(result.session.stroke.lower())
    distance = result.session.distance.replace(" m", "").strip()
    if stroke and distance:
        event = f"{distance} {stroke}"
        best = [p for p in context.pbs if p.get("event") == event and p.get("seconds")]
        if best:
            used.personal_best_event = event
            used.personal_best_s = float(min(p["seconds"] for p in best))
    if not used.goals:
        used.notes.append(
            "The profile has no goals yet, so nothing is ranked by what matters most to "
            "this swimmer."
        )
    if used.swim_level:
        used.notes.append(
            f"Level ({used.swim_level}) is recorded but does not change any finding: no "
            "reference values per level have been verified."
        )
    return used


# ---------- history ----------


def compatibility(now: AnalysisResult, before: AnalysisResult) -> list[str]:
    """Reasons two analyses may not be compared; empty when they may."""
    reasons = []
    a, b = now.session, before.session
    if not a.stroke or a.stroke.lower() != b.stroke.lower():
        reasons.append(
            f"Different stroke ({b.stroke or 'not given'} then, {a.stroke or 'not given'} now)."
        )
    if not a.camera or a.camera.lower() != b.camera.lower():
        reasons.append(
            f"Different filming angle ({b.camera or 'not given'} then, {a.camera or 'not given'} now)."
        )
    if a.distance != b.distance:
        reasons.append(
            f"Different distance ({b.distance or 'not given'} then, {a.distance or 'not given'} now)."
        )
    if now.schema_version != before.schema_version:
        reasons.append(
            f"Measured with a different version of the analysis ({before.schema_version} "
            f"then, {now.schema_version} now): the numbers are not defined the same way."
        )
    for which, r in (("this", now), ("the earlier", before)):
        if r.quality.grade is QualityGrade.INSUFFICIENT:
            reasons.append(f"The swimmer could not be followed well enough in {which} clip.")
    rate_now, rate_before = _metric(now, "stroke_rate"), _metric(before, "stroke_rate")
    if _passed(rate_now) and _passed(rate_before):
        if abs(rate_now.value - rate_before.value) > MAX_PACE_DIFFERENCE * rate_before.value:
            reasons.append(
                f"A different effort: {rate_before.value:.1f} cycles/min then, "
                f"{rate_now.value:.1f} now. A sprint and an easy swim are not the same task."
            )
    elif not reasons:
        reasons.append(
            "Stroke rate was not measured reliably in both clips, so the effort cannot be matched."
        )
    return reasons


def _cv_error(cv: float, n: int) -> float:
    """Rough sampling error of a coefficient of variation from n cycles (percentage points)."""
    return cv / np.sqrt(2 * max(1, n - 1))


def change(key: str, now: AnalysisResult, before: PriorSession) -> MetricChange | None:
    """One metric, this swim against an earlier one; None when either did not pass its checks
    (or, for picture measurements, when either clip's camera view changed)."""
    a, b = _metric(now, key), _metric(before.result, key)
    if not _passed(a) or not _passed(b):
        return None
    if key in GEOMETRIC and (_view_changing(now) or _view_changing(before.result)):
        return None
    frame = 1.0 / min(_fps(now), _fps(before.result))
    spread = lambda m: (m.high - m.low) if m.low is not None and m.high is not None else 0.0  # noqa: E731
    if key == "rhythm_variation":
        floor = 100.0 * TIMING_FRAMES * frame / _metric(now, "cycle_duration").value
        error = np.hypot(_cv_error(a.value, a.n_cycles), _cv_error(b.value, b.n_cycles))
        threshold = 2 * error + floor
    elif key == "cycle_duration":
        threshold = max(TIMING_FRAMES * frame, (spread(a) + spread(b)) / 2)
    elif key == "stroke_rate":
        threshold = max(
            a.value * TIMING_FRAMES * frame / (60.0 / a.value), (spread(a) + spread(b)) / 2
        )
    else:
        threshold = max(2 * RESOLUTION[key], (spread(a) + spread(b)) / 2)
    return MetricChange(
        metric_key=key,
        video_id=before.video_id,
        before=b.value,
        now=a.value,
        unit=a.unit,
        threshold=round(float(threshold), 2),
        changed=abs(a.value - b.value) > threshold,
    )


# ---------- observations ----------


def _odd_cycles(duration: Metric, fps: float) -> list:
    values = np.array([s.value for s in duration.samples])
    if len(values) == 0:
        return []
    median = float(np.median(values))
    limit = max(ODD_CYCLE_FRAMES / fps, ODD_CYCLE_SHARE * median)
    return [s for s in duration.samples if abs(s.value - median) > limit]


def _observations(result: AnalysisResult) -> list[Finding]:
    out: list[Finding] = []
    fps = _fps(result)
    rate, duration, rhythm = (
        _metric(result, k) for k in ("stroke_rate", "cycle_duration", "rhythm_variation")
    )

    def klass(*metrics: Metric) -> str:
        return "measured" if all(_passed(m) for m in metrics) else "context_only"

    if rate and rate.value is not None and duration and duration.value is not None:
        out.append(
            Finding(
                id="obs.stroke_tempo",
                rule_id="obs.stroke_tempo",
                level="observation",
                category="timing",
                title="Stroke tempo",
                description=f"{rate.value:.1f} full arm cycles per minute, one cycle every "
                f"{duration.value:.2f} s, from {duration.n_cycles} cycles.",
                metric_keys=["stroke_rate", "cycle_duration"],
                evidence=[_evidence(rate), _evidence(duration)],
                evidence_class=klass(rate, duration),
                limitations=[
                    "A tempo is not good or bad by itself: it depends on the distance, the "
                    "effort and the swimmer.",
                    "Swim speed was not measured, so nothing is said about distance per stroke.",
                ],
                withheld=[NO_NORM],
            )
        )
    if rhythm and rhythm.value is not None and duration and duration.samples:
        floor = 100.0 * TIMING_FRAMES / fps / duration.value
        times = [s.value for s in duration.samples]
        odd = _odd_cycles(duration, fps)
        steady = rhythm.value <= floor
        out.append(
            Finding(
                id="obs.rhythm",
                rule_id="obs.rhythm",
                level="observation",
                category="timing",
                title="Rhythm steady, as far as the video can time it"
                if steady
                else "Cycle time varied from cycle to cycle",
                description=(
                    f"Cycle times ran from {min(times):.2f} to {max(times):.2f} s (variation "
                    f"{rhythm.value:.1f}%). "
                    + (
                        f"That is within what {fps:.0f} frames per second can time (about {floor:.1f}%)."
                        if steady
                        else f"The video can time differences down to about {floor:.1f}%; "
                        f"{len(odd)} of {len(times)} cycles {'was' if len(odd) == 1 else 'were'} clearly off the middle value."
                    )
                ),
                metric_keys=["rhythm_variation", "cycle_duration"],
                evidence=[
                    _evidence(rhythm),
                    FindingEvidence(
                        metric_key="cycle_duration",
                        label="Cycles clearly off the middle value",
                        unit="s",
                        n_cycles=len(odd),
                        status=duration.status.value,
                        samples=odd,
                    ),
                ],
                evidence_class=klass(rhythm, duration),
                limitations=[
                    "Variation between cycles is not a weakness by itself: a breath, a turn "
                    "or a change of pace all change a cycle.",
                    *(
                        []
                        if not _view_changing(result)
                        else [
                            "The camera view changed during the clip, which makes the timing of cycles seen at an angle less certain."
                        ]
                    ),
                ],
                withheld=[NO_NORM],
            )
        )
    change_ = _metric(result, "cycle_time_change")
    if change_ and change_.value is not None:
        out.append(
            Finding(
                id="obs.tempo_through_the_clip",
                rule_id="obs.tempo_through_the_clip",
                level="observation",
                category="timing",
                title="Cycle time from the start to the end of the clip",
                description=f"The last third's cycles took {change_.value:+.2f} s compared with the first third's."
                + (f" {change_.reason}" if change_.reason else ""),
                metric_keys=["cycle_time_change"],
                evidence=[_evidence(change_)],
                evidence_class=klass(change_),
                limitations=["A change within one short clip is not evidence of fatigue."],
                withheld=[NO_NORM],
            )
        )

    body = [
        (
            "obs.body_line",
            "body_line_angle",
            "Body line against the direction of travel",
            "positive means the feet are lower than the shoulders",
        ),
        (
            "obs.leg_line",
            "leg_line_angle",
            "Legs against the trunk line",
            "negative means the legs sit above the trunk line carried on past the hips",
        ),
        ("obs.head", "head_height", "Head against the trunk line", "0 is in line with the trunk"),
    ]
    for fid, key, title, reading in body:
        m = _metric(result, key)
        if not m or m.value is None:
            continue
        spread = (m.high - m.low) if m.low is not None and m.high is not None else 0.0
        within = spread <= 2 * RESOLUTION[key]
        limits = [
            "Measured in the picture from one camera; it describes this clip, not how the "
            "swimmer always swims.",
        ]
        if m.status is MetricStatus.LIMITED:
            limits.insert(0, f"Limited measurement: {m.reason}")
        if _view_changing(result):
            limits.insert(
                0,
                "The camera view changed during the clip. The cycles filmed at an angle were "
                "left out, but the rest may still be affected, so this is shown for "
                "information only.",
            )
        if m.excluded_cycles:
            limits.append(f"{m.excluded_cycles} stroke cycles filmed at an angle were left out.")
        out.append(
            Finding(
                id=fid,
                rule_id=fid,
                level="observation",
                category="body_position",
                title=title,
                description=f"{_num(m.value, m.unit)} across {m.n_cycles} stroke cycles ({reading}). "
                + (
                    "It stayed the same from cycle to cycle, within what the measurement can tell apart."
                    if within
                    else f"It differed between cycles (middle half {_num(m.low, m.unit)} to {_num(m.high, m.unit)})."
                ),
                metric_keys=[key],
                evidence=[_evidence(m)],
                evidence_class="context_only" if _view_changing(result) else klass(m),
                limitations=limits,
                withheld=[
                    NO_NORM,
                    "Whether a different value would be better for this swimmer is not known.",
                ],
            )
        )

    arm = [
        m for m in (_metric(result, k) for k in sorted(CONTEXT_ONLY)) if m and m.value is not None
    ]
    if arm:
        out.append(
            Finding(
                id="obs.arm_pull_context",
                rule_id="obs.arm_pull_context",
                level="observation",
                category="arm",
                title="Arm pull measurements (for information only)",
                description="; ".join(f"{m.label.lower()} {_num(m.value, m.unit)}" for m in arm)
                + f", from the {arm[0].side} arm, the one nearer the camera.",
                metric_keys=[m.key for m in arm],
                evidence=[_evidence(m) for m in arm],
                evidence_class="context_only",
                limitations=[
                    "The wrist is often placed wrongly near the end of the push, and only a "
                    "small part of the swim gives arm points that can be used.",
                    "Only one arm is measured, in the picture, from one camera.",
                ],
                withheld=["Arm measurements are not used to find issues or priorities yet."],
            )
        )
    return out


# ---------- issue rules ----------


def _rule_uneven_rhythm(result: AnalysisResult) -> tuple[RuleStatus, Finding | None]:
    rule = RULE["timing.uneven_rhythm"]
    duration, rhythm = _metric(result, "cycle_duration"), _metric(result, "rhythm_variation")

    def status(state: str, reason: str) -> RuleStatus:
        return RuleStatus(rule_id=rule.rule_id, title=rule.title, state=state, reason=reason)

    if not _passed(duration) or not _passed(rhythm):
        why = "Cycle time or rhythm variation did not pass its own checks for this clip."
        return status("not_applicable", why), None
    if duration.n_cycles < MIN_CYCLES_RHYTHM_ISSUE:
        return status(
            "not_applicable",
            f"Needs at least {MIN_CYCLES_RHYTHM_ISSUE} reliable cycles of one arm; this clip has {duration.n_cycles}.",
        ), None
    if _view_changing(result):
        return status(
            "suppressed",
            "The camera view changed during the clip. Cycles seen at an angle are timed less surely, so uneven timing here may come from the filming.",
        ), None
    odd = _odd_cycles(duration, _fps(result))
    share = len(odd) / duration.n_cycles
    if len(odd) < MIN_ODD_CYCLES or share < MIN_ODD_SHARE:
        return status(
            "not_triggered",
            f"{len(odd)} of {duration.n_cycles} cycles were off the rhythm; the rule needs at least {MIN_ODD_CYCLES} and {MIN_ODD_SHARE:.0%}.",
        ), None
    finding = Finding(
        id="issue.timing.uneven_rhythm",
        rule_id=rule.rule_id,
        level="issue_candidate",
        category="timing",
        title="Uneven stroke rhythm in this clip",
        description=f"{len(odd)} of {duration.n_cycles} stroke cycles were clearly longer or "
        f"shorter than this swim's own middle cycle time of {duration.value:.2f} s. Worth a "
        "look at those moments in the video.",
        metric_keys=list(rule.metric_keys),
        evidence=[
            _evidence(rhythm),
            FindingEvidence(
                metric_key="cycle_duration",
                label="Cycles off the rhythm",
                unit="s",
                n_cycles=len(odd),
                status=duration.status.value,
                samples=odd,
            ),
        ],
        limitations=[
            "From one clip. A breath, a turn, a push-off or a change of pace all make a cycle longer or shorter.",
            "The comparison is with this swim's own rhythm, not with a standard.",
        ],
        actionable=True,
        withheld=["Whether an even rhythm would make this swimmer faster is not known.", NO_NORM],
    )
    return status(
        "triggered", f"{len(odd)} of {duration.n_cycles} cycles ({share:.0%}) were off the rhythm."
    ), finding


def _rule_rhythm_history(
    result: AnalysisResult, compatible: list[PriorSession]
) -> tuple[RuleStatus, Finding | None]:
    rule = RULE["history.rhythm_less_steady"]

    def status(state: str, reason: str) -> RuleStatus:
        return RuleStatus(rule_id=rule.rule_id, title=rule.title, state=state, reason=reason)

    if not compatible:
        return status(
            "not_applicable", "There is no compatible earlier swim to compare with."
        ), None
    changes = [c for c in (change("rhythm_variation", result, p) for p in compatible) if c]
    if not changes:
        return status(
            "not_applicable",
            "Rhythm variation did not pass its checks in both this swim and an earlier one.",
        ), None
    latest = changes[0]
    if _view_changing(result):
        return status(
            "suppressed",
            "The camera view changed during this clip, so its cycle timing is less sure.",
        ), None
    if not latest.changed or latest.now <= latest.before:
        return status(
            "not_triggered",
            f"{latest.before:.1f}% then, {latest.now:.1f}% now: not more than the {latest.threshold:.1f} points that could be noise.",
        ), None
    rhythm = _metric(result, "rhythm_variation")
    also = [c for c in changes[1:] if c.changed and c.now > c.before]
    finding = Finding(
        id="issue.history.rhythm_less_steady",
        rule_id=rule.rule_id,
        level="issue_candidate",
        category="history",
        title="Stroke rhythm less steady than in your earlier comparable swim",
        description=f"Rhythm variation was {latest.before:.1f}% in the earlier swim and is "
        f"{latest.now:.1f}% now, more than the {latest.threshold:.1f} points that the "
        "measurement itself could account for."
        + (
            f" The same holds against {len(also)} more earlier swim{'s' if len(also) != 1 else ''}."
            if also
            else ""
        ),
        metric_keys=list(rule.metric_keys),
        evidence=[_evidence(rhythm)],
        changes=changes,
        limitations=[
            "Two clips of a few cycles each. Where in the length the clip was filmed changes the rhythm too.",
            "Compared only with swims of the same stroke, distance, filming angle and a similar stroke rate.",
        ],
        actionable=True,
        withheld=["This does not say why the rhythm changed, or that it cost time.", NO_NORM],
    )
    return status(
        "triggered",
        f"{latest.before:.1f}% then, {latest.now:.1f}% now (threshold {latest.threshold:.1f}).",
    ), finding


# ---------- priorities ----------


def _priorities(issues: list[Finding], used: ContextUsed) -> tuple[list[PriorityCandidate], str]:
    ranked = []
    for f in issues:
        rule = RULE[f.rule_id]
        cycles = max(
            (e.n_cycles for e in f.evidence if e.metric_key == "rhythm_variation"), default=0
        )
        odd = next((e.n_cycles for e in f.evidence if e.label == "Cycles off the rhythm"), 0)
        earlier = sum(1 for c in f.changes if c.changed and c.now > c.before)
        matched = [g for g in used.goals if g in rule.goal_keys]
        goals = [GOALS[g] for g in matched]
        main = used.primary_goal in matched
        ratio = max(
            ((abs(c.now - c.before) / c.threshold) for c in f.changes if c.threshold), default=0.0
        )
        factors = [
            PriorityFactor(
                name="Evidence",
                points=2 if cycles >= 8 else 1 if cycles >= 4 else 0,
                detail=f"{cycles} reliable stroke cycles behind it.",
            ),
            PriorityFactor(
                name="Repeated in the clip",
                points=(2 if odd / cycles >= 0.5 else 1) if cycles and odd else 0,
                detail=f"{odd} of {cycles} cycles." if odd else "Not a per-cycle pattern.",
            ),
            PriorityFactor(
                name="Seen across swims",
                points=min(2, earlier),
                detail=f"Holds against {earlier} earlier comparable swim{'s' if earlier != 1 else ''}.",
            ),
            PriorityFactor(
                name="Your goals",
                points=(3 if main else 2) if goals else 0,
                detail=(
                    f"Matches your main goal: {GOALS[used.primary_goal]}."
                    if main
                    else f"Matches a goal you set: {goals[0]}."
                )
                if goals
                else "No matching goal on the profile.",
            ),
            PriorityFactor(
                name="Size against noise",
                points=2 if ratio >= 2 else 1 if ratio >= 1.5 else 0,
                detail=f"{ratio:.1f} times the smallest difference that counts."
                if ratio
                else "Not a comparison with an earlier swim.",
            ),
            PriorityFactor(
                name="Outside evidence",
                points=0,
                detail="None verified yet: no points are given for expected effect on speed.",
            ),
        ]
        # A priority needs more than one clip's pattern: it has to repeat across swims or
        # match something the swimmer asked for.
        if earlier >= 1 or goals:
            ranked.append((sum(p.points for p in factors), f, factors))
    ranked.sort(key=lambda item: (-item[0], item[1].id))
    out = [
        PriorityCandidate(rank=i + 1, finding_id=f.id, title=f.title, score=score, factors=factors)
        for i, (score, f, factors) in enumerate(ranked[:MAX_PRIORITIES])
    ]
    if out:
        return (
            out,
            "Ranked by the points shown: evidence, repetition, your goals and size against noise. No points for expected effect on speed, because none has been verified.",
        )
    if issues:
        return (
            [],
            "Something may need attention, but nothing is ranked as a priority: that needs the same pattern in another comparable swim, or a goal on your profile it matches.",
        )
    return [], "No improvement priorities: the measurements from this clip do not support any."


# ---------- undetermined ----------


def _undetermined(
    result: AnalysisResult, used: ContextUsed, sessions: list[SessionComparison]
) -> list[Undetermined]:
    out: list[Undetermined] = []
    if not result.metrics:
        out.append(
            Undetermined(
                key="no_metrics",
                title="Technique measurements",
                reason="This analysis was made before technique measurements existed. Run the analysis again to get them.",
            )
        )
    view = result.coverage.view if result.coverage else None
    if view and view.status == "changing":
        out.append(
            Undetermined(
                key="camera_view",
                title="Body position through the whole clip",
                reason=f"{view.note} Position and angle measurements from those parts are not interpreted, and nothing about posture is concluded from changes that follow the camera.",
            )
        )
    if result.coverage and result.coverage.camera_side.arm is None and result.metrics:
        out.append(
            Undetermined(
                key="camera_side",
                title="Arm pull",
                reason=result.coverage.camera_side.reason
                or "It is not clear which arm is nearer the camera.",
            )
        )
    # One entry per reason, so a clip nothing could be measured from says so once.
    by_reason: dict[str, list[tuple[str, str]]] = {}
    for m in result.metrics:
        if m.status is MetricStatus.UNAVAILABLE:
            by_reason.setdefault(m.reason, []).append((m.key, m.label))
    measured = {m.key for m in result.metrics}
    for u in result.unavailable:
        if u.key not in measured:
            by_reason.setdefault(u.reason, []).append((u.key, u.label))
    for reason, items in by_reason.items():
        out.append(
            Undetermined(
                key=items[0][0] if len(items) == 1 else f"{items[0][0]}+{len(items) - 1}",
                title=", ".join(label for _, label in items),
                reason=reason,
            )
        )
    limited = [
        m for m in result.metrics if m.status is MetricStatus.LIMITED and m.key not in CONTEXT_ONLY
    ]
    for m in limited:
        out.append(
            Undetermined(
                key=f"limited.{m.key}",
                title=f"{m.label}: what it means",
                kind="interpretation",
                reason=f"Measured, but limited ({m.reason}) It is shown as an observation and not used to find issues.",
            )
        )
    if not any(s.compatible for s in sessions):
        why = "This is a baseline: there is no earlier swim that can be compared with it."
        if sessions:
            why += f" {len(sessions)} earlier swim{'s were' if len(sessions) != 1 else ' was'} set aside as not comparable."
        out.append(
            Undetermined(
                key="no_history",
                title="Change since earlier swims",
                kind="interpretation",
                reason=why,
            )
        )
    out.append(
        Undetermined(
            key="no_reference",
            title="Whether any value is good or bad",
            kind="interpretation",
            reason="No reference values have been verified for these measurements, so nothing is compared with other swimmers or with an ideal.",
        )
    )
    if not used.goals:
        out.append(
            Undetermined(
                key="no_goals",
                title="What matters most to you",
                kind="interpretation",
                reason="The profile has no goals yet, so findings are not ranked by them.",
            )
        )
    return out


# ---------- entry point ----------


def interpret(
    result: AnalysisResult,
    video_id: str,
    analysis_id: str = "",
    context: SwimmerContext | None = None,
    history: list[PriorSession] | None = None,
) -> Interpretation:
    """Interpret one stored analysis. `history`: the swimmer's earlier analyses, most recent
    first; incompatible ones are listed with the reason and not used."""
    used = _context(result, context)
    sessions, compatible = [], []
    for prior in history or []:
        reasons = (
            compatibility(result, prior.result)
            if result.metrics and prior.result.metrics
            else ["One of the two analyses has no technique measurements."]
        )
        sessions.append(
            SessionComparison(
                video_id=prior.video_id,
                analysis_id=prior.analysis_id,
                recorded_at=prior.recorded_at,
                compatible=not reasons,
                reasons=reasons,
                synthetic=prior.synthetic,
            )
        )
        if not reasons:
            compatible.append(prior)

    observations = _observations(result) if result.metrics else []
    for key in sorted(DESCRIBE_AND_COMPARE):
        changes = [c for c in (change(key, result, p) for p in compatible) if c]
        if not changes:
            continue
        latest, m = changes[0], _metric(result, key)
        observations.append(
            Finding(
                id=f"obs.history.{key}",
                rule_id="obs.history",
                level="observation",
                category="history",
                title=f"{m.label}: {'changed' if latest.changed else 'no clear change'} since your earlier comparable swim",
                description=f"{_num(latest.before, m.unit)} then, {_num(latest.now, m.unit)} now. "
                + (
                    f"The difference is more than the {_num(latest.threshold, m.unit)} that the measurement itself could account for."
                    if latest.changed
                    else f"Differences under {_num(latest.threshold, m.unit)} cannot be told from measurement noise."
                ),
                metric_keys=[key],
                evidence=[_evidence(m)],
                changes=changes,
                limitations=[
                    "Compared only with swims of the same stroke, distance, filming angle and a similar stroke rate.",
                    "A change between two clips does not say what caused it.",
                ],
                withheld=["Not judged as better or worse.", NO_NORM],
            )
        )

    rules, issues = [], []
    if result.metrics:
        for status, finding in (
            _rule_uneven_rhythm(result),
            _rule_rhythm_history(result, compatible),
        ):
            rules.append(status)
            if finding:
                finding.context_used = [
                    GOALS[g] for g in used.goals if g in RULE[finding.rule_id].goal_keys
                ]
                issues.append(finding)
    else:
        rules += [
            RuleStatus(
                rule_id=r.rule_id,
                title=r.title,
                state="not_applicable",
                reason="This analysis has no technique measurements.",
            )
            for r in RULES
            if r.active
        ]
    rules += [
        RuleStatus(
            rule_id=r.rule_id,
            title=r.title,
            state="pending_validation",
            reason=f"Not active. It needs {r.needs_reference}.",
        )
        for r in RULES
        if not r.active
    ]
    priorities, note = _priorities(issues, used)
    undetermined = _undetermined(result, used, sessions)
    baseline = not compatible
    summary = (
        f"{len(observations)} observation{'s' if len(observations) != 1 else ''}, "
        f"{len(issues)} that may need attention, {len(priorities)} improvement "
        f"priorit{'ies' if len(priorities) != 1 else 'y'}. "
        + (
            "Baseline: nothing earlier to compare with."
            if baseline
            else f"Compared with {len(compatible)} earlier swim{'s' if len(compatible) != 1 else ''}."
        )
    )
    return Interpretation(
        rules_version=RULES_VERSION,
        video_id=video_id,
        analysis_id=analysis_id,
        analysis_schema_version=result.schema_version,
        baseline=baseline,
        context=used,
        observations=observations,
        issue_candidates=issues,
        priorities=priorities,
        priorities_note=note,
        undetermined=undetermined,
        sessions=sessions,
        rules=rules,
        summary=summary,
    )
