"""Real-inference acceptance test: run YOLO11m + RTMW-x on one video inside the worker image.

    python scripts/gpu_acceptance.py \\
        --video-url https://upload.wikimedia.org/wikipedia/commons/9/9b/Front_Crawl_Underwater.webm \\
        --video-sha256 ce32d556ba1399b9dd5000f9a079475ca33377a9280cf30619a566ff8e9523c3 \\
        --out-dir /out

THIS IS THE ONLY TEST THAT COUNTS AS REAL INFERENCE, AND IT HAS NOT BEEN RUN. It needs the
worker image (models installed, a GPU) and the owner's approval (docs/PHASE_9B_EXECUTION.md).
It uses no Firebase and no user data: one public video, fetched from its public URL and
checked against its known SHA-256 before anything runs.

What it writes to --out-dir, and prints as one JSON document to the log:

  acceptance.json               everything measured (below)
  <video sha256>.rawpose.npz    the new RawPose, named exactly like the saved reference

It records and never hides: the model check with file hashes and library versions, whether
the GPU was really used, frames per second (detector and pose apart), peak memory of the
process and of the GPU, and the analysis the existing pipeline makes of the new pose. When
a reference RawPose is given (--reference) it also compares the two, with the tolerances it
was judged against; otherwise that comparison is done afterwards on the developer's machine
with scripts/compare_pose.py, which needs no models.

Exit status: 0 ran (and, with a reference, within tolerance); 1 outside tolerance or not
comparable; 3 models not usable; 4 the video could not be fetched or is not the expected
file; 5 the run asked for a GPU and did not use one.
"""
# ruff: noqa: E501

import argparse
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from aquatrack.analysis.pipeline import analyze
from aquatrack.analysis.pose.compare import Tolerances, compare_metrics, compare_raw_pose
from aquatrack.analysis.pose.manifest import sha256_of
from aquatrack.analysis.pose.sources import PRECOMPUTED_SUFFIX, LocalModelPoseSource
from aquatrack.analysis.video import read_video_info, video_identity
from aquatrack.api.jobs import check_video_limits, rss_mb
from aquatrack.contracts import ModelConfig, RawPose, SessionInfo

SESSION = SessionInfo(stroke="Freestyle", camera="Underwater", distance="50 m")


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


def fetch_video(url: str, expected_sha256: str, dest: Path) -> Path:
    """Download the public test video and refuse anything that is not the expected file."""
    if not url.startswith("https://"):
        raise SystemExit("the test video must come from an https URL")
    request = urllib.request.Request(url, headers={"User-Agent": "aquatrack-acceptance/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response, dest.open("wb") as out:  # noqa: S310
        while block := response.read(1 << 20):
            out.write(block)
    return dest


def run(args, source=None) -> tuple[int, dict]:
    """The test itself. `source` can be replaced in unit tests; a real run never passes it."""
    report: dict = {"real_inference": source is None, "video": {}}
    args.out_dir.mkdir(parents=True, exist_ok=True)

    video = args.video
    if video is None:
        # Kept out of --out-dir (which may be a mounted bucket): the video is input, not a
        # result, and is removed with the temp folder when the job ends.
        video = Path(tempfile.mkdtemp(prefix="aquatrack-acceptance-")) / "input-video"
        try:
            fetch_video(args.video_url, args.video_sha256, video)
        except Exception as e:
            report["error"] = f"video download failed ({type(e).__name__})"
            return 4, report
    actual = sha256_of(video)
    report["video"] = {"sha256": actual, "bytes": video.stat().st_size}
    if args.video_sha256 and actual != args.video_sha256:
        report["error"] = "the video is not the expected file (SHA-256 differs)"
        return 4, report

    source = source or LocalModelPoseSource(ModelConfig.from_env())
    started = time.perf_counter()
    check = source.preflight()
    report["preflight"] = check.to_dict()
    report["model_load_s"] = round(time.perf_counter() - started, 2)
    if not check.ok:
        return 3, report
    if source.device.startswith("cuda") and "CUDAExecutionProvider" not in check.providers:
        report["error"] = "a GPU was requested and is not in use"
        return 5, report

    problem = check_video_limits(video)
    if problem is not None:
        report["error"] = f"the worker's own limits refuse this video: {problem.code}"
        return 4, report
    identity = video_identity(video)
    info = read_video_info(video)
    peak_gpu = [gpu_memory_mb() or 0.0]

    def on_frame(done, total):
        if done % 50 == 0:
            peak_gpu[0] = max(peak_gpu[0], gpu_memory_mb() or 0.0)

    started = time.perf_counter()
    raw = source.get_raw_pose(video, identity, "acceptance", progress=on_frame)
    inference_s = time.perf_counter() - started
    stats = getattr(getattr(source, "_estimator", None), "last_run", None)
    frames = len(raw.frame_indices)
    report["run"] = {
        "frames": frames,
        "video_seconds": round(info.duration_s, 2),
        "inference_s": round(inference_s, 2),
        "frames_per_second": round(frames / inference_s, 2) if inference_s > 0 else None,
        "detector_s_per_frame": round(stats.detect_s / max(stats.frames, 1), 4) if stats else None,
        "pose_s_per_frame": round(stats.pose_s / max(stats.frames, 1), 4) if stats else None,
        "peak_process_memory_mb": round(rss_mb(), 1),
        "peak_gpu_memory_mb": peak_gpu[0] or None,
        "device": source.device,
    }
    if raw.meta.video.sha256 != actual:
        report["error"] = "the RawPose is not tied to the video that was read"
        return 4, report
    report["models"] = {
        "detector": raw.meta.detector.model_dump(),
        "pose": raw.meta.pose.model_dump(),
        "config": raw.meta.config.model_dump(),
    }
    pose_path = args.out_dir / f"{actual}{PRECOMPUTED_SUFFIX}"
    raw.save(pose_path)
    report["artifacts"] = {"raw_pose": pose_path.name, "report": "acceptance.json"}

    result, _ = analyze(raw, "acceptance", SESSION, identity, video_path=video)
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
        ref_result, _ = analyze(reference, "reference", SESSION, identity, video_path=video)
        rows = compare_metrics(new_metrics, [m.model_dump(mode="json") for m in ref_result.metrics])
        report["metric_comparison"] = rows
        flagged = [r for r in rows if r.get("flag")]
        if not comparison.comparable:
            report["verdict"] = "not comparable"
        elif comparison.within_tolerance and not flagged:
            report["verdict"] = "within tolerance"
        else:
            report["verdict"] = "differences to explain"
        status = 0 if report["verdict"] == "within tolerance" else 1
    else:
        report["verdict"] = "ran; compare with the reference using scripts/compare_pose.py"
    return status, report


def main(argv: list[str] | None = None, source=None) -> int:
    parser = argparse.ArgumentParser()
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument("--video", type=Path, help="a video file already in the container")
    where.add_argument("--video-url", help="public https URL of the test video")
    parser.add_argument("--video-sha256", default="", help="the SHA-256 the video must have")
    parser.add_argument("--reference", type=Path, help="the saved RawPose of the same video")
    parser.add_argument("--out-dir", type=Path, default=Path("acceptance-out"))
    args = parser.parse_args(argv)
    if args.video_url and not args.video_sha256:
        parser.error("--video-url needs --video-sha256")
    status, report = run(args, source)
    report["exit_status"] = status
    (args.out_dir / "acceptance.json").write_text(json.dumps(report, indent=2, default=str))
    # One line, so it can be read back whole from the job's log.
    print("ACCEPTANCE_REPORT " + json.dumps(report, sort_keys=True, default=str))
    if status:
        print(
            f"acceptance test did not pass: {report.get('error') or report.get('verdict')}",
            file=sys.stderr,
        )
    return status


if __name__ == "__main__":
    raise SystemExit(main())
