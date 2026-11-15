"""Analysis v1: raw pose -> processed pose -> quality report and basic stroke timing.

Deterministic and model-free: it runs the same on pose data from Colab, a local model or a
future worker. It reports only what was measured; everything else is listed as unavailable
with the reason.
"""

import numpy as np

from aquatrack import __version__
from aquatrack.analysis.metrics.cycles import StrokeAnalysis, analyze_strokes, main_stretch
from aquatrack.analysis.processing import Processed, process
from aquatrack.analysis.quality import build_quality_report
from aquatrack.contracts import (
    AnalysisResult,
    Measurement,
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
)

# Measures the Project Overview asks for that analysis v1 does not report yet.
NOT_YET = "Not part of analysis v1. It will be added once it has been checked on real swims."
PENDING = [
    ("head_position", "Head position"),
    ("body_alignment", "Body alignment"),
    ("arm_trajectory", "Arm trajectory"),
    ("breathing_timing", "Breathing timing"),
    ("kick_rhythm", "Kick rhythm"),
    ("stroke_consistency", "Stroke consistency"),
    ("left_right_balance", "Left-right balance"),
    ("section_changes", "Changes across the swim"),
]
# Arm cycles are found from the arm turning around the shoulder, which breaststroke doesn't do.
UNSUPPORTED_STROKES = {"breaststroke"}


def _stroke_summary(
    strokes: StrokeAnalysis, seconds, session: SessionInfo
) -> tuple[StrokeSummary, list[Measurement]]:
    if session.stroke.lower() in UNSUPPORTED_STROKES:
        return (
            StrokeSummary(
                measurable=False,
                reason=f"Stroke cycles can't be counted for {session.stroke.lower()} yet: "
                "the arms sweep instead of turning all the way around.",
            ),
            [],
        )
    cycles = [
        StrokeCycleOut(
            arm=c.arm,
            start_s=seconds(c.start),
            end_s=seconds(c.end),
            duration_s=round(c.duration_s, 3),
            trusted=c.trusted,
            reason=c.reason,
            section=c.section,
        )
        for c in strokes.cycles
    ]
    counts = {
        arm: sum(c.trusted and c.arm == arm for c in strokes.cycles) for arm in ("left", "right")
    }
    total = sum(counts.values())
    if total == 0:
        return (
            StrokeSummary(
                measurable=False,
                reason="No complete arm cycle could be followed reliably in this clip.",
                cycle_count=counts,
                cycles=cycles,
            ),
            [],
        )
    rates = {
        arm: None if np.isnan(r) else round(float(r), 1) for arm, r in strokes.rate_per_min.items()
    }
    # A count is only a count when every cycle was followed. If some were unclear (merged,
    # split or hidden), the reliable ones still give a rate, but their number would undercount.
    complete = all(c.trusted for c in strokes.cycles)
    summary = StrokeSummary(
        measurable=True,
        cycle_count=counts,
        stroke_count=total if complete else None,
        cycles_per_min=rates,
        cycles=cycles,
    )
    trusted = [c for c in strokes.cycles if c.trusted]
    arms_used = [arm for arm, n in counts.items() if n]
    basis = f"{total} reliable arm cycles ({', '.join(f'{counts[a]} {a}' for a in arms_used)})"
    measurements = [
        Measurement(
            key="stroke_rate",
            label="Stroke rate",
            value=round(strokes.stroke_rate_per_min, 1),
            unit="cycles/min",
            basis=basis,
        ),
        Measurement(
            key="cycle_duration",
            label="Time per stroke cycle",
            value=round(float(np.median([c.duration_s for c in trusted])), 2),
            unit="s",
            basis=basis,
        ),
    ]
    if complete:
        measurements.append(
            Measurement(
                key="stroke_count",
                label="Arm strokes counted",
                value=float(total),
                unit="",
                basis="every arm cycle in the clip was followed, left and right",
            )
        )
    return summary, measurements


def analyze(
    raw: RawPose,
    video_id: str,
    session: SessionInfo | None = None,
    video: VideoIdentity | None = None,
) -> tuple[AnalysisResult, ProcessedPose]:
    """Run analysis v1. `video` is the uploaded file's identity (defaults to the one recorded
    with the raw pose); the caller is responsible for checking that they match."""
    session = session or SessionInfo()
    video = video or raw.meta.video
    if video is None:
        raise ValueError("The pose data does not say which video it belongs to.")
    processed: Processed = process(raw)
    clean = processed.clean
    strokes = analyze_strokes(clean)

    def seconds(i: int) -> float:
        return round(float(raw.timestamps_s[i]), 3)

    stroke, measurements = _stroke_summary(strokes, seconds, session)
    reliable = sum(c.trusted for c in strokes.cycles) if stroke.measurable else 0
    quality = build_quality_report(raw, processed.pose, reliable, session, video.frame_count)

    unavailable = [Unavailable(key=k, label=label, reason=NOT_YET) for k, label in PENDING]
    unavailable.append(
        Unavailable(
            key="body_rotation",
            label="Body rotation",
            reason="Needs a clip filmed from overhead or from the front.",
        )
    )
    if not stroke.measurable:
        unavailable.insert(
            0, Unavailable(key="stroke_rate", label="Stroke rate", reason=stroke.reason)
        )
    elif stroke.stroke_count is None:
        unclear = sum(not c.trusted for c in strokes.cycles)
        unavailable.insert(
            0,
            Unavailable(
                key="stroke_count",
                label="Stroke count",
                reason=f"{unclear} of {len(strokes.cycles)} arm cycles could not be followed "
                "clearly, so a count would come out too low. The stroke rate uses the clear ones.",
            ),
        )
    if quality.grade is QualityGrade.INSUFFICIENT and stroke.measurable:
        # Too little reliable data to stand behind the numbers: withhold rather than guess.
        reason = "The swimmer could not be followed reliably enough in this clip."
        stroke = StrokeSummary(
            measurable=False, reason=reason, cycle_count=stroke.cycle_count, cycles=stroke.cycles
        )
        measurements = []
        unavailable.insert(0, Unavailable(key="stroke_rate", label="Stroke rate", reason=reason))
    quality.unavailable = unavailable

    stretch = main_stretch(clean)
    trusted_durations = [c.duration_s for c in strokes.cycles if c.trusted]
    timing = Timing(
        clip_duration_s=round(video.duration_s, 2),
        swim_start_s=seconds(stretch[0]) if stretch else None,
        swim_end_s=seconds(stretch[1]) if stretch else None,
        sections=[
            SectionOut(name=s.name, start_s=seconds(s.start), end_s=seconds(s.end))
            for s in strokes.sections
        ],
        median_cycle_s=round(float(np.median(trusted_durations)), 2)
        if trusted_durations and stroke.measurable
        else None,
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
    )
    return result, processed.pose
