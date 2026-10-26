"""Run whole-body pose on a video and save the result next to it.

    uv run python -m aquatrack.analysis.pose.cli VIDEO [--step N] [--overlay] [--device mps]

Writes VIDEO_STEM.wholebody.npz (and VIDEO_STEM.overlay.mp4 with --overlay), then prints
how often the swimmer, hands and feet were found and the time per frame.
"""

import argparse
from pathlib import Path

import numpy as np

from aquatrack.analysis.pose.overlay import default_overlay_path, render_overlay
from aquatrack.analysis.pose.rtmw_backend import RTMW_ONNX, RtmwEstimator, YoloPersonDetector
from aquatrack.analysis.pose.wholebody import (
    BODY,
    LEFT_FOOT,
    LEFT_HAND,
    RIGHT_FOOT,
    RIGHT_HAND,
    WholeBodySequence,
    default_pose_path,
)


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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("video", type=Path)
    parser.add_argument("--step", type=int, default=1, help="analyze every Nth frame")
    parser.add_argument("--onnx", type=Path, default=RTMW_ONNX)
    parser.add_argument("--detector", type=Path, default=None, help="YOLO weights for boxes")
    parser.add_argument("--device", default="cpu", help="pose model: cpu, or mps for CoreML")
    parser.add_argument("--detector-device", default=None, help="YOLO: cpu or mps")
    parser.add_argument("--overlay", action="store_true", help="also render a skeleton video")
    args = parser.parse_args(argv)

    detector = YoloPersonDetector(args.detector, device=args.detector_device)
    estimator = RtmwEstimator(args.onnx, detector=detector, device=args.device)
    pose = estimator.estimate_wholebody(args.video, step=args.step)
    print(f"pose: {pose.save(default_pose_path(args.video))}")
    if args.overlay:
        print(f"overlay: {render_overlay(args.video, pose, default_overlay_path(args.video))}")

    stats = estimator.last_run
    print(f"{len(pose)} frames analyzed (step {args.step}), detector {detector.name}")
    for part, value in coverage(pose).items():
        print(f"  {part:>11}: {value:5.1f}%")
    steady = np.median(stats.timings[1:]) if len(stats.timings) > 1 else float("nan")
    print(
        f"seconds per frame: {stats.seconds_per_frame:.3f} mean, {steady:.3f} median "
        f"(detect {stats.detect_s / max(stats.frames, 1):.3f}, "
        f"pose {stats.pose_s / max(stats.frames, 1):.3f})"
    )


if __name__ == "__main__":
    main()
