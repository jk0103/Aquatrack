"""Real-inference acceptance test: run YOLO11m + RTMW-x on one video inside the worker image
and compare the result with the saved Phase 1 reference.

    python scripts/gpu_acceptance.py --video /work/front_crawl_underwater.webm \
        --reference /work/reference.rawpose.npz --out /work/acceptance.json

THIS IS THE ONLY TEST THAT COUNTS AS REAL INFERENCE, and it has not been run. It needs the
worker image (models installed, GPU present) and the owner's approval of the budget in
docs/GPU_ACCEPTANCE_TEST.md. It does not touch Firebase: stage 1 of the plan is the models
alone. Stage 2 (the worker against a Firebase project) is `python -m aquatrack.worker`.

It reports, and never hides: the model check, frames per second (detector and pose apart),
peak memory of the process and of the GPU, how the new pose differs from the reference with
the tolerances it was judged against, and the metrics of the two analyses side by side.
Exit status: 0 within tolerance, 1 outside it or not comparable, 3 models not usable.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from aquatrack.analysis.pipeline import analyze
from aquatrack.analysis.pose.compare import Tolerances, compare_metrics, compare_raw_pose
from aquatrack.analysis.pose.sources import LocalModelPoseSource
from aquatrack.analysis.video import read_video_info, video_identity
from aquatrack.api.jobs import check_video_limits, rss_mb
from aquatrack.contracts import ModelConfig, RawPose, SessionInfo


def gpu_memory_mb() -> float | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout
        return max(float(x) for x in out.split())
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--reference", type=Path, help="the saved RawPose of the same video")
    parser.add_argument("--out", type=Path, default=Path("acceptance.json"))
    parser.add_argument("--save-pose", type=Path, help="where to write the new RawPose")
    args = parser.parse_args()

    report: dict = {"video": args.video.name, "real_inference": True}
    source = LocalModelPoseSource(ModelConfig.from_env())
    started = time.perf_counter()
    check = source.preflight()
    report["preflight"] = check.to_dict()
    report["model_load_s"] = round(time.perf_counter() - started, 2)
    if not check.ok:
        args.out.write_text(json.dumps(report, indent=2))
        print(f"models not usable: {check.error_code}: {check.error}", file=sys.stderr)
        return 3

    problem = check_video_limits(args.video)
    if problem is not None:
        raise SystemExit(f"the test video is refused by the worker's own limits: {problem.code}")
    identity = video_identity(args.video)
    info = read_video_info(args.video)
    peak_gpu = [gpu_memory_mb() or 0.0]

    def on_frame(done, total):
        if done % 50 == 0:
            peak_gpu[0] = max(peak_gpu[0], gpu_memory_mb() or 0.0)

    started = time.perf_counter()
    raw = source.get_raw_pose(args.video, identity, "acceptance", progress=on_frame)
    inference_s = time.perf_counter() - started
    stats = source._estimator.last_run
    report["run"] = {
        "frames": stats.frames,
        "video_seconds": round(info.duration_s, 2),
        "inference_s": round(inference_s, 2),
        "frames_per_second": round(stats.frames / inference_s, 2) if inference_s else None,
        "detector_s_per_frame": round(stats.detect_s / max(stats.frames, 1), 4),
        "pose_s_per_frame": round(stats.pose_s / max(stats.frames, 1), 4),
        "peak_process_memory_mb": round(rss_mb(), 1),
        "peak_gpu_memory_mb": peak_gpu[0] or None,
        "device": source.device,
    }
    if args.save_pose:
        raw.save(args.save_pose)
    session = SessionInfo(stroke="Freestyle", camera="Underwater", distance="50 m")
    result, _ = analyze(raw, "acceptance", session, identity, video_path=args.video)
    new_metrics = [m.model_dump(mode="json") for m in result.metrics]
    report["analysis"] = {
        "grade": result.quality.grade.value,
        "valid_pose_pct": result.quality.valid_pose_pct,
        "metrics": {m["key"]: {"value": m["value"], "status": m["status"]} for m in new_metrics},
    }

    status = 0
    if args.reference:
        reference = RawPose.load(args.reference)
        comparison = compare_raw_pose(raw, reference, Tolerances())
        report["pose_comparison"] = comparison.to_dict()
        report["tolerances"] = Tolerances().__dict__
        ref_result, _ = analyze(reference, "reference", session, identity, video_path=args.video)
        report["metric_comparison"] = compare_metrics(
            new_metrics, [m.model_dump(mode="json") for m in ref_result.metrics]
        )
        flagged = [r for r in report["metric_comparison"] if r.get("flag")]
        report["verdict"] = (
            "within tolerance"
            if comparison.within_tolerance and not flagged
            else "differences to explain"
            if comparison.comparable
            else "not comparable"
        )
        status = 0 if report["verdict"] == "within tolerance" else 1
    else:
        report["verdict"] = "ran; no reference given to compare with"
    args.out.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("run", "verdict")}, indent=2))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
