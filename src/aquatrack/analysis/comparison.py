"""Comparing a swimmer's own sessions: metric by metric, with the reasons when it can't be done.

Everything here reads stored `AnalysisResult`s only. No video, pose data or model is needed,
and nothing is stored: a comparison is recomputed from the analyses it names.

A session is ruled out as a whole only for reasons that affect every number (another stroke,
another filming angle, another distance, a clearly different effort, a clip in which the
swimmer could not be followed). Otherwise each metric is decided on its own: one may be
comparable while another is not.

The outcome words are neutral: increased, decreased, no clearly measurable change,
insufficient evidence, not comparable. Nothing here says better or worse.
"""
# ruff: noqa: E501

from dataclasses import dataclass

from aquatrack.analysis.interpretation import (
    CONTEXT_ONLY,
    DESCRIBE_AND_COMPARE,
    GEOMETRIC,
    PriorSession,
    _metric,
    _passed,
    _view_changing,
    change,
    compatibility,
)
from aquatrack.contracts import (
    AnalysisResult,
    CheckpointFollowUp,
    MetricComparison,
    MetricStatus,
    Progress,
    ProgressMetric,
    ProgressPoint,
    ProgressSeries,
    QualityGrade,
    SessionComparisonResult,
    SessionSummary,
)

# The analysis schema in which each metric got its current definition. Two analyses of
# different versions are compared on a metric only if both are at least this new: an older
# value was computed differently and there is no validated conversion.
DEFINED_SINCE = {
    "stroke_rate": "1.1",
    "cycle_duration": "1.1",
    "rhythm_variation": "1.1",
    # 1.2 left out cycles filmed at an angle, which changes what these are a median of.
    "body_line_angle": "1.2",
    "leg_line_angle": "1.2",
    "head_height": "1.2",
    "pull_depth": "1.2",
    "elbow_angle_min": "1.2",
    "pull_path_variation": "1.2",
}
RELATIVE = {"stroke_rate", "cycle_duration"}  # a percentage means something for these
ORDER = [
    "stroke_rate",
    "cycle_duration",
    "rhythm_variation",
    "body_line_angle",
    "leg_line_angle",
    "head_height",
    "pull_depth",
    "elbow_angle_min",
    "pull_path_variation",
]
LABELS = {
    "stroke_rate": ("Stroke rate", "cycles/min"),
    "cycle_duration": ("Time per stroke cycle", "s"),
    "rhythm_variation": ("Rhythm variation", "%"),
    "body_line_angle": ("Body line angle", "deg"),
    "leg_line_angle": ("Legs against the trunk line", "deg"),
    "head_height": ("Head against the trunk line", "trunk lengths"),
    "pull_depth": ("Pull depth", "trunk lengths"),
    "elbow_angle_min": ("Elbow bend in the pull (2D)", "deg"),
    "pull_path_variation": ("Pull path variation", "trunk lengths"),
}
MIN_SERIES_FOR_REPEAT = 2


@dataclass
class Session:
    """One analysed video of the swimmer, as read from the store."""

    video_id: str
    result: AnalysisResult
    analysis_id: str = ""
    recorded_at: str = ""
    synthetic: bool = False


def _version(text: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in text.split("."))
    except ValueError:
        return (0,)


def summary(s: Session) -> SessionSummary:
    r = s.result
    rate = _metric(r, "stroke_rate")
    return SessionSummary(
        video_id=s.video_id,
        analysis_id=s.analysis_id,
        recorded_at=s.recorded_at,
        stroke=r.session.stroke,
        camera=r.session.camera,
        distance=r.session.distance,
        pool_length=r.session.pool_length,
        schema_version=r.schema_version,
        tracking_grade=r.quality.grade.value,
        view_status=r.coverage.view.status if r.coverage and r.coverage.view else "",
        stroke_rate=rate.value if rate else None,
        synthetic=s.synthetic,
    )


def session_reasons(now: AnalysisResult, before: AnalysisResult) -> list[str]:
    """Reasons that rule out every metric. The analysis version is not one of them: it is
    decided per metric."""
    if not now.metrics or not before.metrics:
        return [
            "One of the two analyses was made before technique measurements existed. Analyse that video again to compare it."
        ]
    return [
        r
        for r in compatibility(now, before)
        if not r.startswith("Measured with a different version")
    ]


def _one(key: str, now: Session, before: Session, blocked: list[str]) -> MetricComparison:
    label, unit = LABELS[key]
    a, b = _metric(now.result, key), _metric(before.result, key)
    out = MetricComparison(
        metric_key=key,
        label=label,
        unit=unit,
        state="not_comparable",
        previous=b.value if b else None,
        current=a.value if a else None,
        previous_status=b.status.value if b else "",
        current_status=a.status.value if a else "",
        previous_cycles=b.n_cycles if b else 0,
        current_cycles=a.n_cycles if a else 0,
    )
    if blocked:
        out.reasons = blocked
        return out
    if key in CONTEXT_ONLY:
        out.reasons = [
            "Arm measurements are shown for information only and are not compared between swims yet: the arm points are not reliable enough."
        ]
        return out
    if key not in DESCRIBE_AND_COMPARE:
        out.reasons = [
            "This number depends on how long the clip is, so it is not compared between swims."
        ]
        return out
    va, vb = now.result.schema_version, before.result.schema_version
    if va != vb and min(_version(va), _version(vb)) < _version(DEFINED_SINCE[key]):
        out.reasons = [
            f"This measurement was defined differently before analysis version {DEFINED_SINCE[key]} (the two swims were analysed with {vb} and {va}), and there is no validated way to convert it. Analysing the older video again would make them comparable."
        ]
        return out
    if key in GEOMETRIC and (_view_changing(now.result) or _view_changing(before.result)):
        out.reasons = [
            "The camera view changed during one of the clips, so positions and angles in the picture are not compared."
        ]
        return out
    if not _passed(a) or not _passed(b):
        out.state = "insufficient_evidence"
        for which, m in (("earlier", b), ("later", a)):
            if m is None or m.status is MetricStatus.UNAVAILABLE:
                out.reasons.append(
                    f"Not measured in the {which} swim"
                    + (f": {m.reason}" if m and m.reason else ".")
                )
            elif m.status is MetricStatus.LIMITED:
                out.reasons.append(f"Limited in the {which} swim: {m.reason}")
        return out
    c = change(key, now.result, PriorSession(video_id=before.video_id, result=before.result))
    if c is None:  # every reason above has been ruled out; be safe anyway
        out.state, out.reasons = "insufficient_evidence", ["The two values could not be compared."]
        return out
    out.change = round(c.now - c.before, 3)
    out.threshold = c.threshold
    if key in RELATIVE and c.before:
        out.relative_pct = round(100.0 * (c.now - c.before) / c.before, 1)
    out.state = (
        ("increased" if c.now > c.before else "decreased") if c.changed else "no_clear_change"
    )
    out.limitations = [
        "A difference shows that the number moved, not why, and not whether it is better.",
        "Each value comes from a few stroke cycles of one clip.",
    ]
    return out


def compare(now: Session, before: Session) -> SessionComparisonResult:
    """`before` against `now` (the later swim), metric by metric."""
    blocked = session_reasons(now.result, before.result)
    keys = [k for k in ORDER if _metric(now.result, k) or _metric(before.result, k)]
    metrics = [_one(k, now, before, blocked) for k in keys]
    moved = [m for m in metrics if m.state in ("increased", "decreased")]
    same = [m for m in metrics if m.state == "no_clear_change"]
    comparable = bool(moved or same)
    if blocked:
        text = "These two swims cannot be compared: " + " ".join(blocked)
    elif not comparable:
        text = "No measurement could be compared between these two swims. Each one says why."
    else:
        text = f"{len(moved)} measurement{'s' if len(moved) != 1 else ''} changed by more than the measurement can account for, {len(same)} showed no clearly measurable change, and {len(metrics) - len(moved) - len(same)} could not be compared."
    return SessionComparisonResult(
        previous=summary(before),
        current=summary(now),
        comparable=comparable,
        session_reasons=blocked,
        metrics=metrics,
        summary=text,
    )


# ---------- checkpoints followed up by a later video ----------


def follow_up(checkpoints: list[dict], source: Session, now: Session) -> list[CheckpointFollowUp]:
    """What `now` says about the checkpoints stored with an earlier video's feedback."""
    comparison = compare(now, source)
    by_key = {m.metric_key: m for m in comparison.metrics}
    out = []
    for cp in checkpoints:
        cid, title = str(cp.get("id", "")), str(cp.get("title", ""))
        base = dict(
            checkpoint_id=cid,
            title=title,
            source_video_id=source.video_id,
            created_at=str(cp.get("created_at", "")),
        )
        r = now.result
        if cid == "cp.side_view":
            ok = (
                r.quality.grade is not QualityGrade.INSUFFICIENT
                and not _view_changing(r)
                and bool(r.coverage and r.coverage.camera_side.arm)
            )
            out.append(
                CheckpointFollowUp(
                    **base,
                    state="comparable_measurement_available" if ok else "cannot_evaluate",
                    explanation="This video was filmed side-on with a steady view, so its position and angle measurements can be used."
                    if ok
                    else "This video does not give a steady side view either, so the checkpoint is still open.",
                )
            )
            continue
        if cid == "cp.longer_clip":
            m = _metric(r, "cycle_duration")
            n = m.n_cycles if m else 0
            ok = n >= 6
            out.append(
                CheckpointFollowUp(
                    **base,
                    state="comparable_measurement_available" if ok else "cannot_evaluate",
                    explanation=f"This video has {n} full cycles of one arm"
                    + (
                        ", enough to look at rhythm."
                        if ok
                        else "; at least 6 are needed, so the checkpoint is still open."
                    ),
                )
            )
            continue
        keys = [k for k in cp.get("metric_keys", []) if k in by_key]
        found = [by_key[k] for k in keys]
        moved = [m for m in found if m.state in ("increased", "decreased")]
        same = [m for m in found if m.state == "no_clear_change"]
        if comparison.session_reasons:
            state, why = (
                "cannot_evaluate",
                "This video cannot be compared with the one the checkpoint came from: "
                + " ".join(comparison.session_reasons),
            )
        elif moved:
            state = "measurable_change_observed"
            why = (
                "; ".join(
                    f"{m.label.lower()} {m.state} from {m.previous:g} to {m.current:g} {m.unit}".strip()
                    for m in moved
                )
                + ". That is more than the measurement can account for. It says the number moved, not that it is better or worse."
            )
        elif same:
            state, why = (
                "no_clear_measurable_change",
                "The matching measurements differ by less than the measurement can tell apart.",
            )
        else:
            state, why = (
                "cannot_evaluate",
                "The measurements this checkpoint needs could not be compared: "
                + " ".join(dict.fromkeys(r for m in found for r in m.reasons))
                if found
                else "This video has none of the measurements the checkpoint needs.",
            )
        out.append(CheckpointFollowUp(**base, state=state, explanation=why, metrics=found))
    return out


# ---------- progress across all sessions ----------


def build_progress(sessions: list[Session], videos: int) -> Progress:
    """Group the swimmer's analysed sessions into series that may share a line, oldest first.
    A session joins the first series whose first session it is comparable with; otherwise it
    starts its own. Nothing is interpolated and incompatible sessions are never joined."""
    ordered = sorted(sessions, key=lambda s: s.recorded_at)
    groups: list[list[Session]] = []
    left_out: list[Session] = []
    reasons: dict[str, list[str]] = {}
    for s in ordered:
        if not s.result.metrics:
            left_out.append(s)
            reasons[s.video_id] = [
                "Analysed before technique measurements existed. Analyse this video again to include it."
            ]
            continue
        if s.result.quality.grade is QualityGrade.INSUFFICIENT:
            left_out.append(s)
            reasons[s.video_id] = ["The swimmer could not be followed well enough in this clip."]
            continue
        home = next((g for g in groups if not session_reasons(s.result, g[0].result)), None)
        if home is None:
            groups.append([s])
        else:
            home.append(s)

    series = []
    for n, group in enumerate(groups):
        first = group[0]
        metrics = []
        for key in ORDER:
            if key not in DESCRIBE_AND_COMPARE:
                continue
            label, unit = LABELS[key]
            points = []
            for s in group:
                m = _metric(s.result, key)
                comparable = (
                    _one(key, s, first, []).state != "not_comparable" if s is not first else True
                )
                if (
                    not _passed(m)
                    or not comparable
                    or (key in GEOMETRIC and _view_changing(s.result))
                ):
                    continue
                points.append(
                    ProgressPoint(
                        video_id=s.video_id,
                        recorded_at=s.recorded_at,
                        value=m.value,
                        low=m.low,
                        high=m.high,
                        cycles=m.n_cycles,
                    )
                )
            if not points:
                continue
            by_id = {s.video_id: s for s in group}
            overall = (
                _one(key, by_id[points[-1].video_id], by_id[points[0].video_id], [])
                if len(points) >= 2
                else None
            )
            metrics.append(
                ProgressMetric(
                    metric_key=key, label=label, unit=unit, points=points, overall=overall
                )
            )
        series.append(
            ProgressSeries(
                key=f"series-{n + 1}",
                stroke=first.result.session.stroke,
                camera=first.result.session.camera,
                distance=first.result.session.distance,
                sessions=[summary(s) for s in group],
                metrics=metrics,
            )
        )

    repeated = []
    usable = [s for s in ordered if s.result.metrics]
    changing = sum(_view_changing(s.result) for s in usable)
    if changing >= MIN_SERIES_FOR_REPEAT:
        repeated.append(
            f"The camera view changed during {changing} of your {len(usable)} analysed videos, which keeps body position from being compared. Filming side-on with a steady view would help."
        )
    short = sum(
        1
        for s in usable
        if (m := _metric(s.result, "cycle_duration")) and m.value is not None and m.n_cycles < 6
    )
    if short >= MIN_SERIES_FOR_REPEAT:
        repeated.append(
            f"{short} of your analysed videos have fewer than 6 stroke cycles of one arm, too few to look at rhythm. Longer clips would help."
        )
    weak = sum(s.result.quality.grade is QualityGrade.INSUFFICIENT for s in ordered)
    if weak >= MIN_SERIES_FOR_REPEAT:
        repeated.append(
            f"In {weak} videos the swimmer could not be followed well enough to measure anything."
        )

    baseline = not any(len(g) >= 2 for g in groups)
    if not ordered:
        note = "No analysed videos yet."
    elif baseline:
        note = "This is your baseline. Trends need at least two videos of the same stroke and distance, filmed the same way at a similar effort."
    else:
        note = "Only videos that may be compared share a line. A change means a number moved by more than the measurement can account for; it is not a judgement."
    return Progress(
        videos=videos,
        analyzed=len(ordered),
        baseline=baseline,
        series=series,
        not_in_any_series=[summary(s) for s in left_out],
        not_included_reasons=reasons,
        repeated_limitations=repeated,
        note=note,
    )
