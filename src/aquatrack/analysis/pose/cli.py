"""Run whole-body pose on a video, clean it, find stroke cycles, and save it all next to it.

    uv run python -m aquatrack.analysis.pose.cli VIDEO [--step N] [--overlay] [--device mps]

Writes, next to VIDEO:
  VIDEO_STEM.wholebody.npz   raw 133-point pose from the model
  VIDEO_STEM.clean.npz       cleaned points, confidences and what cleanup did to each
  VIDEO_STEM.cycles.json     stroke cycles, stroke rate and swim sections
  VIDEO_STEM.overlay.mp4     with --overlay: cleaned skeleton and a marker at each cycle
--reuse skips the model and starts from an existing .wholebody.npz.
"""

import argparse
from pathlib import Path

import numpy as np

from aquatrack.analysis.metrics.cycles import (
    StrokeAnalysis,
    analyze_strokes,
    default_cycles_path,
)
from aquatrack.analysis.pose.cleanup import (
    L_WRIST,
    R_WRIST,
    CleanPose,
    Fix,
    clean,
    default_clean_path,
)
from aquatrack.analysis.pose.overlay import OverlayEvent, default_overlay_path, render_overlay
from aquatrack.analysis.pose.wholebody import (
    BODY,
    FACE,
    LEFT_FOOT,
    LEFT_HAND,
    RIGHT_FOOT,
    RIGHT_HAND,
    WholeBodySequence,
    default_pose_path,
)

_DRAWN = [i for i in range(133) if i not in FACE]


def coverage(pose: WholeBodySequence) -> dict[str, float]:
    """Percent of analyzed frames where each part was found."""

    def pct(mask: np.ndarray) -> float:
        return 100.0 * float(mask.mean()) if len(mask) else 0.0

    left_hand, right_hand = pose.found(LEFT_HAND), pose.found(RIGHT_HAND)
    left_foot, right_foot = pose.found(LEFT_FOOT), pose.found(RIGHT_FOOT)
    return {
        "swimmer": pct(pose.has_swimmer()),
        "body": pct(pose.found(BODY)),
        "left hand": pct(left_hand),
        "right hand": pct(right_hand),
        "both hands": pct(left_hand & right_hand),
        "left foot": pct(left_foot),
        "right foot": pct(right_foot),
        "both feet": pct(left_foot & right_foot),
    }


def cleanup_summary(pose: CleanPose) -> dict[str, int]:
    """How many frames cleanup touched, over body, feet and hands (the face is ignored)."""
    flags = pose.flags[:, _DRAWN]

    def frames(mask: Fix) -> int:
        return int(((flags & mask) > 0).any(axis=1).sum())

    return {
        "frames": len(pose),
        "whole frame dropped": frames(Fix.BAD_FRAME),
        "points dropped (impossible)": frames(Fix.IMPOSSIBLE),
        "points dropped (spike)": frames(Fix.SPIKE),
        "left/right swapped": frames(Fix.SWAPPED),
        "changed or dropped": frames(Fix.BAD_FRAME | Fix.IMPOSSIBLE | Fix.SPIKE | Fix.SWAPPED),
        "gaps filled": frames(Fix.FILLED),
    }


def cycle_events(strokes: StrokeAnalysis, pose: CleanPose) -> list[OverlayEvent]:
    events, counts = [], {"left": 0, "right": 0}
    for c in strokes.cycles:
        counts[c.arm] += 1
        text = f"{c.arm.capitalize()} stroke {counts[c.arm]}"
        if not c.trusted:
            text += " (unsure)"
        wrist = L_WRIST if c.arm == "left" else R_WRIST
        events.append(OverlayEvent(int(pose.frame_indices[c.start]), text, c.arm, wrist))
    return events


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("video", type=Path)
    parser.add_argument("--step", type=int, default=1, help="analyze every Nth frame")
    parser.add_argument("--onnx", type=Path, default=None, help="RTMW weights")
    parser.add_argument("--detector", type=Path, default=None, help="YOLO weights for boxes")
    parser.add_argument("--device", default="cpu", help="pose model: cpu, or mps for CoreML")
    parser.add_argument("--detector-device", default=None, help="YOLO: cpu or mps")
    parser.add_argument("--reuse", action="store_true", help="start from the saved raw pose")
    parser.add_argument("--overlay", action="store_true", help="also render a skeleton video")
    parser.add_argument("--raw-overlay", action="store_true", help="draw the uncleaned points")
    args = parser.parse_args(argv)

    raw_path = default_pose_path(args.video)
    if args.reuse and raw_path.exists():
        raw = WholeBodySequence.load(raw_path)
        print(f"reused: {raw_path}")
    else:
        # Imported here so --reuse works without the model weights or the pose extra.
        from aquatrack.analysis.pose.rtmw_backend import (
            RTMW_ONNX,
            RtmwEstimator,
            YoloPersonDetector,
        )

        detector = YoloPersonDetector(args.detector, device=args.detector_device)
        estimator = RtmwEstimator(args.onnx or RTMW_ONNX, detector=detector, device=args.device)
        raw = estimator.estimate_wholebody(args.video, step=args.step)
        print(f"pose: {raw.save(raw_path)}")
        stats = estimator.last_run
        steady = np.median(stats.timings[1:]) if len(stats.timings) > 1 else float("nan")
        print(
            f"{len(raw)} frames analyzed (step {args.step}), detector {detector.name}; "
            f"seconds per frame: {stats.seconds_per_frame:.3f} mean, {steady:.3f} median "
            f"(detect {stats.detect_s / max(stats.frames, 1):.3f}, "
            f"pose {stats.pose_s / max(stats.frames, 1):.3f})"
        )

    cleaned = clean(raw)
    strokes = analyze_strokes(cleaned)
    print(f"clean: {cleaned.save(default_clean_path(args.video))}")
    print(f"cycles: {strokes.save(default_cycles_path(args.video), cleaned)}")
    if args.overlay:
        if args.raw_overlay:
            out = render_overlay(args.video, raw.frame_indices, raw.keypoints, _overlay(args))
        else:
            out = render_overlay(
                args.video,
                cleaned.frame_indices,
                cleaned.image_points(),
                _overlay(args),
                min_value=1e-6,
                events=cycle_events(strokes, cleaned),
            )
        print(f"overlay: {out}")

    print("found (raw):")
    for part, value in coverage(raw).items():
        print(f"  {part:>26}: {value:5.1f}% of frames")
    print(f"cleanup{' (mirrored so the head is on the right)' if cleaned.flipped else ''}:")
    for what, count in cleanup_summary(cleaned).items():
        print(f"  {what:>26}: {count}")
    print("stroke cycles:")
    for arm, rate in strokes.rate_per_min.items():
        arm_cycles = [c for c in strokes.cycles if c.arm == arm]
        trusted = sum(c.trusted for c in arm_cycles)
        rate_text = "n/a" if np.isnan(rate) else f"{rate:.1f}/min"
        print(f"  {arm:>5}: {len(arm_cycles)} cycles, {trusted} trusted, rate {rate_text}")
    for c in strokes.cycles:
        if not c.trusted:
            print(f"  skipped {c.arm} cycle at frame {c.start}: {c.reason}")


def _overlay(args) -> Path:
    return default_overlay_path(args.video)


if __name__ == "__main__":
    main()
