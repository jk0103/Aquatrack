"""Analysis: raw pose -> processed pose -> stroke cycles -> metrics -> structured result.

Deterministic and model-free: it runs the same on pose data from Colab, a local model or a
future worker. Stages, each a separate module with a structured hand-over:

  processing    raw pose -> cleaned pose, joint states, swimmer segments
  quality       tracking quality (was the swimmer followed, were joints placed)
  cycles        underwater pulls and stroke cycles
  usability     which arm faces the camera, which arm points may be used
  biomechanics  metrics, each with its own reliability
  (here)        coverage summary and the versioned AnalysisResult

It reports only what was measured; everything else is listed as unavailable with the reason.
"""

from pathlib import Path

import numpy as np

from aquatrack import __version__
from aquatrack.analysis import biomechanics
from aquatrack.analysis.horizon import horizontal
from aquatrack.analysis.metrics.cycles import StrokeAnalysis, analyze_strokes, main_stretch
from aquatrack.analysis.processing import Processed, process
from aquatrack.analysis.quality import build_quality_report
from aquatrack.analysis.usability import arm_observations, arm_use, camera_side, view_check
from aquatrack.contracts import (
    AnalysisCoverage,
    AnalysisResult,
    CameraSide,
    CycleCompleteness,
    Measurement,
    Metric,
    MetricStatus,
    PartialCycleOut,
    ProcessedPose,
    QualityGrade,
    RawPose,
    SectionOut,
    SessionInfo,
    StrokeCycleOut,
    StrokeSummary,
    Timing,
    Unavailable,
    VideoIdentity,
    ViewSuitability,
)

# Arm cycles are found from the arm turning around the shoulder, which breaststroke doesn't do.
UNSUPPORTED_STROKES = {"breaststroke"}


def _stroke_summary(
    strokes: StrokeAnalysis, seconds, arm: str | None, metrics: list[Metric], reason: str
) -> StrokeSummary:
    cycles = [
        StrokeCycleOut(
            arm=c.arm,
            start_s=seconds(c.start),
            end_s=seconds(c.end),
            duration_s=round(c.duration_s, 3),
            trusted=c.trusted,
            reason=c.reason,
            section=c.section,
            kind=c.kind,
            timed_from=c.timing,
        )
        for c in strokes.cycles
    ]
    partial = [
        PartialCycleOut(arm=p.arm, start_s=seconds(p.start), end_s=seconds(p.end))
        for p in strokes.partial
    ]
    counts = {
        side: sum(c.trusted and c.arm == side for c in strokes.cycles) for side in ("left", "right")
    }
    if reason or arm is None:
        return StrokeSummary(
            measurable=False,
            reason=reason or "No complete arm cycle could be followed reliably in this clip.",
            cycle_count=counts,
            cycles=cycles,
            partial=partial,
        )
    count = next(m for m in metrics if m.key == "cycle_count")
    return StrokeSummary(
        measurable=True,
        cycle_count=counts,
        cycles_per_min={
            side: None if np.isnan(r) else round(float(r), 1)
            for side, r in strokes.rate_per_min.items()
        },
        cycles=cycles,
        partial=partial,
        counted_arm=arm,
        counted_cycles=None if count.value is None else int(count.value),
    )


def _coverage(
    grade: QualityGrade,
    side: CameraSide,
    arms,
    strokes: StrokeAnalysis,
    arm: str | None,
    metrics: list[Metric],
) -> AnalysisCoverage:
    every = [c for c in strokes.cycles if c.arm == arm] if arm else []
    reliable = sum(c.trusted for c in every)
    partial = sum(p.arm == arm for p in strokes.partial)
    count = next((m for m in metrics if m.key == "cycle_count"), None)
    measurable = bool(count and count.value is not None)
    if not reliable:
        note = "No whole stroke cycle could be followed."
    elif measurable:
        note = f"All {reliable} whole cycles of the {arm} arm in the clip were followed."
    elif len(every) > reliable:
        note = (
            f"{reliable} of {len(every)} {arm}-arm cycles were followed clearly; "
            f"{len(every) - reliable} were unclear."
        )
    else:
        note = f"{reliable} whole cycles of the {arm} arm were followed. {count.reason}"
    cycles = CycleCompleteness(
        arm=arm,
        detected=len(every),
        reliable=reliable,
        ambiguous=len(every) - reliable,
        partial=partial,
        count_measurable=measurable,
        status="none" if not reliable else "complete" if measurable else "partial",
        note=note,
    )
    n = {status: sum(m.status is status for m in metrics) for status in MetricStatus}
    shown = n[MetricStatus.RELIABLE] + n[MetricStatus.LIMITED]
    return AnalysisCoverage(
        tracking_grade=grade,
        camera_side=side,
        arms=arms,
        cycles=cycles,
        metrics_reliable=n[MetricStatus.RELIABLE],
        metrics_limited=n[MetricStatus.LIMITED],
        metrics_unavailable=n[MetricStatus.UNAVAILABLE],
        summary=f"{shown} of {len(metrics)} measurements could be made from this clip: "
        f"{n[MetricStatus.RELIABLE]} met their reliability criteria, "
        f"{n[MetricStatus.LIMITED]} are limited.",
    )


def analyze(
    raw: RawPose,
    video_id: str,
    session: SessionInfo | None = None,
    video: VideoIdentity | None = None,
    video_path: str | Path | None = None,
) -> tuple[AnalysisResult, ProcessedPose]:
    """Run the analysis. `video` is the uploaded file's identity (defaults to the one recorded
    with the raw pose); the caller is responsible for checking that they match. `video_path`,
    when given, lets the level reference be read from the pool's lines."""
    session = session or SessionInfo()
    video = video or raw.meta.video
    if video is None:
        raise ValueError("The pose data does not say which video it belongs to.")
    processed: Processed = process(raw)
    clean = processed.clean
    strokes = analyze_strokes(clean)

    def seconds(i: int) -> float:
        return round(float(raw.timestamps_s[i]), 3)

    reliable = sum(c.trusted for c in strokes.cycles)
    quality = build_quality_report(raw, processed.pose, reliable, session, video.frame_count)

    # Reasons to stand behind no number at all.
    withhold = ""
    if session.stroke.lower() in UNSUPPORTED_STROKES:
        withhold = (
            f"Stroke cycles can't be found for {session.stroke.lower()} yet: "
            "the arms sweep instead of turning all the way around."
        )
    elif quality.grade is QualityGrade.INSUFFICIENT:
        withhold = "The swimmer could not be followed reliably enough in this clip."

    side = camera_side(clean, raw.keypoints, strokes, session)
    use = arm_use(clean, strokes)
    stretch = main_stretch(clean)
    frames = np.arange(stretch[0], stretch[1] + 1) if stretch else np.arange(0)
    if len(frames):
        horizon, horizon_source = horizontal(clean, frames, video_path)
    else:
        horizon, horizon_source = np.zeros(len(clean)), "frame horizontal"
    timed = biomechanics.timing_arm(strokes, side)
    view = view_check(clean, [c for c in strokes.cycles if c.trusted and c.arm == timed])
    metrics = biomechanics.measure(
        clean,
        strokes,
        side,
        horizon,
        horizon_source,
        session,
        raw.timestamps_s,
        use,
        view,
        withhold,
    )
    arm = None if withhold else biomechanics.timing_arm(strokes, side)
    stroke = _stroke_summary(strokes, seconds, arm, metrics, withhold)
    if not stroke.measurable:
        quality.reliable_stroke_cycles = 0
    coverage = _coverage(
        quality.grade, side, arm_observations(clean, use, side), strokes, arm, metrics
    )
    coverage.view = ViewSuitability(
        status=view.status,
        smallest_size_share=round(min(view.size_ratio.values()), 2) if view.size_ratio else None,
        cycles_left_out=len(view.unsuitable),
        cycles_checked=len(view.size_ratio),
        note=view.note,
    )

    # Schema 1.0 fields, still filled so older readers and the history list keep working.
    by_key = {m.key: m for m in metrics}
    measurements = [
        Measurement(key=m.key, label=m.label, value=m.value, unit=m.unit, basis=m.basis)
        for m in (by_key["stroke_rate"], by_key["cycle_duration"])
        if m.value is not None
    ]
    unavailable = [
        Unavailable(key=m.key, label=m.label, reason=m.reason)
        for m in metrics
        if m.status is MetricStatus.UNAVAILABLE
    ]
    unavailable += [
        Unavailable(key=key, label=label, reason=reason)
        for key, label, reason in biomechanics.NOT_MEASURED
    ]
    quality.unavailable = unavailable

    timing = Timing(
        clip_duration_s=round(video.duration_s, 2),
        swim_start_s=seconds(stretch[0]) if stretch else None,
        swim_end_s=seconds(stretch[1]) if stretch else None,
        sections=[
            SectionOut(name=s.name, start_s=seconds(s.start), end_s=seconds(s.end))
            for s in strokes.sections
        ],
        median_cycle_s=by_key["cycle_duration"].value,
    )
    result = AnalysisResult(
        engine_version=__version__,
        video_id=video_id,
        video=video,
        session=session,
        config=raw.meta.config,
        detector=raw.meta.detector,
        pose=raw.meta.pose,
        pose_source=raw.meta.provenance.source,
        stroke=stroke,
        timing=timing,
        quality=quality,
        measurements=measurements,
        unavailable=unavailable,
        metrics=metrics,
        coverage=coverage,
    )
    return result, processed.pose
