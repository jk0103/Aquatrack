"""Compare a new RawPose with the saved reference of the same video. Needs no models, no GPU
and no network: it runs on the developer's machine after the acceptance job has finished.

    uv run python scripts/compare_pose.py \\
        --new downloads/<sha256>.rawpose.npz \\
        --reference data/precomputed_pose/<sha256>.rawpose.npz \\
        --video test_videos/public/front_crawl_underwater.webm

It reports how the keypoints, boxes and scores differ, runs the existing analysis pipeline
on both and lists the metrics side by side, and states the tolerances it judged against.
A difference is reported with its likely reasons; it is never rounded away.
Exit status: 0 within tolerance, 1 differences to explain, 2 not comparable.
"""
# ruff: noqa: E501

import argparse
import json
from pathlib import Path

from aquatrack.analysis.pipeline import analyze
from aquatrack.analysis.pose.compare import Tolerances, compare_metrics, compare_raw_pose
from aquatrack.analysis.pose.sources import validate_raw_pose
from aquatrack.analysis.video import video_identity
from aquatrack.contracts import RawPose, SessionInfo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True, help="the video both runs are of")
    parser.add_argument("--out", type=Path, help="write the full report here as JSON")
    args = parser.parse_args(argv)

    new, reference = RawPose.load(args.new), RawPose.load(args.reference)
    identity = video_identity(args.video)
    validate_raw_pose(new, identity)  # the new pose must belong to this exact video
    comparison = compare_raw_pose(new, reference, Tolerances())
    report = {
        "new": {
            "detector": new.meta.detector.model_dump(),
            "pose": new.meta.pose.model_dump(),
            "provenance": new.meta.provenance.model_dump(),
        },
        "reference": {
            "detector": reference.meta.detector.model_dump(),
            "pose": reference.meta.pose.model_dump(),
            "provenance": reference.meta.provenance.model_dump(),
        },
        "tolerances": Tolerances().__dict__,
        "pose_comparison": comparison.to_dict(),
    }
    status = 2
    if comparison.comparable:
        session = SessionInfo(stroke="Freestyle", camera="Underwater", distance="50 m")
        a, _ = analyze(new, "new", session, identity, video_path=args.video)
        b, _ = analyze(reference, "reference", session, identity, video_path=args.video)
        rows = compare_metrics(
            [m.model_dump(mode="json") for m in a.metrics],
            [m.model_dump(mode="json") for m in b.metrics],
        )
        report["metric_comparison"] = rows
        report["grades"] = {"new": a.quality.grade.value, "reference": b.quality.grade.value}
        flagged = [r for r in rows if r.get("flag")]
        ok = comparison.within_tolerance and not flagged and a.quality.grade == b.quality.grade
        report["verdict"] = "within tolerance" if ok else "differences to explain"
        status = 0 if ok else 1
    else:
        report["verdict"] = "not comparable"
    if args.out:
        args.out.write_text(json.dumps(report, indent=2, default=str))
    print(
        json.dumps(
            {k: report[k] for k in ("verdict", "pose_comparison") if k in report},
            indent=2,
            default=str,
        )
    )
    return status


if __name__ == "__main__":
    raise SystemExit(main())
