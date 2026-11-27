"""Readiness of the real inference worker: model manifest and checksums, the pose model's
input/output contract, the GPU check, the start-up preflight, stopping a running inference,
memory and temp-file handling, partial-result clean-up, and the comparison used by the
acceptance test.

NONE OF THIS IS MODEL INFERENCE. Model files here are a few bytes of text, ONNX sessions
and estimators are fakes, and pose data is synthetic. These tests show that the worker
refuses bad models, stops when it must and cleans up after itself. Whether YOLO11m and
RTMW-x actually run in the worker is shown only by scripts/gpu_acceptance.py on a GPU, and
that has not been run."""
# ruff: noqa: E501

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest
from conftest import make_raw_pose
from test_queue import UID, FakeInference, add_video, job, status

from aquatrack import worker
from aquatrack.analysis.pose import manifest, rtmw_backend
from aquatrack.analysis.pose.compare import Tolerances, compare_metrics, compare_raw_pose
from aquatrack.analysis.pose.manifest import ModelError
from aquatrack.analysis.pose.sources import LocalModelPoseSource, PoseSourceError
from aquatrack.analysis.video import video_identity
from aquatrack.api import jobs
from aquatrack.api.jobs import Worker, cancel_analysis, request_analysis, run_job
from aquatrack.api.store import MemoryStore
from aquatrack.contracts import ModelConfig

# ---------- fakes ----------


@dataclass
class Port:
    name: str
    shape: list


class FakeSession:
    """FAKE ONNX Runtime session with the right shapes unless told otherwise."""

    def __init__(self, providers=("CPUExecutionProvider",), inputs=None, outputs=None):
        self._providers = list(providers)
        self._inputs = inputs or [Port("input", [1, 3, 384, 288])]
        self._outputs = outputs or [Port("simcc_x", [1, 133, 576]), Port("simcc_y", [1, 133, 768])]

    def get_inputs(self):
        return self._inputs

    def get_outputs(self):
        return self._outputs

    def get_providers(self):
        return self._providers


class FakeLoaded:
    def __init__(self, session=None, smoke_error=None):
        self.pose_session = session or FakeSession()
        self.smoke_error = smoke_error

    def smoke(self):
        if self.smoke_error:
            raise self.smoke_error
        return "ran on a blank frame (133 points returned)"


def install(tmp_path, with_manifest=True, **content) -> Path:
    """A models folder holding stand-in files (a few bytes each; not model weights)."""
    files = {"yolo11m.pt": b"FAKE detector", "rtmw_x_stock.onnx": b"FAKE pose model"} | content
    entries = {}
    for name, data in files.items():
        (tmp_path / name).write_bytes(data)
        entries[name] = {"sha256": manifest.sha256_of(tmp_path / name), "bytes": len(data)}
    if with_manifest:
        manifest.write_manifest(tmp_path, entries)
    return tmp_path


def check(models, device="cpu", strict=True, load=None):
    return manifest.run_preflight(
        models, "yolo11m.pt", "rtmw_x_stock.onnx", device, strict, load or (lambda *a: FakeLoaded())
    )


# ---------- model files ----------


def test_files_that_match_the_manifest_pass_and_are_recorded_with_their_hashes(tmp_path):
    report = check(install(tmp_path))
    assert report.ok and report.smoke_test.startswith("ran on a blank frame")
    assert [(f["name"], f["verified"]) for f in report.files] == [
        ("yolo11m.pt", True),
        ("rtmw_x_stock.onnx", True),
    ]
    assert all(len(f["sha256"]) == 64 for f in report.files)
    assert report.onnx["outputs"] == {"simcc_x": (1, 133, 576), "simcc_y": (1, 133, 768)}


@pytest.mark.parametrize(
    "damage,code",
    [
        (lambda d: (d / "rtmw_x_stock.onnx").unlink(), "model_missing"),
        (lambda d: (d / "yolo11m.pt").unlink(), "model_missing"),
        (
            lambda d: (d / "rtmw_x_stock.onnx").write_bytes(b"FAKE pose MODEL"),
            "model_checksum_mismatch",
        ),  # same size, altered
        (
            lambda d: (d / "yolo11m.pt").write_bytes(b"swapped for another detector"),
            "model_checksum_mismatch",
        ),
        (lambda d: (d / "manifest.json").unlink(), "model_manifest_missing"),
        (lambda d: (d / "manifest.json").write_text("{not json"), "model_manifest_invalid"),
        (
            lambda d: (d / "manifest.json").write_text(
                json.dumps(
                    {
                        "files": {
                            "yolo11m.pt": json.loads((d / "manifest.json").read_text())["files"][
                                "yolo11m.pt"
                            ]
                        }
                    }
                )
            ),
            "model_not_in_manifest",
        ),
    ],
)
def test_a_missing_altered_or_unlisted_model_file_is_refused_before_anything_loads(
    tmp_path, damage, code
):
    models = install(tmp_path)
    damage(models)
    loaded = []
    report = check(models, load=lambda *a: loaded.append(1) or FakeLoaded())
    assert not report.ok and report.error_code == code
    assert loaded == []  # the models were never loaded
    assert str(tmp_path) not in report.error  # file names only, no paths


def test_outside_strict_mode_an_unlisted_file_loads_but_is_marked_unverified(tmp_path):
    report = check(install(tmp_path, with_manifest=False), strict=False)
    assert report.ok and [f["verified"] for f in report.files] == [False, False]
    assert not check(install(tmp_path, with_manifest=False), strict=True).ok


def test_strict_mode_is_always_on_outside_local_development(monkeypatch):
    monkeypatch.delenv("AQUATRACK_MODELS_STRICT", raising=False)
    for env, expected in (
        ("emulator", False),
        ("test", False),
        ("staging", True),
        ("production", True),
    ):
        monkeypatch.setenv("AQUATRACK_ENV", env)
        assert manifest.is_strict() is expected
    monkeypatch.setenv("AQUATRACK_ENV", "emulator")
    monkeypatch.setenv("AQUATRACK_MODELS_STRICT", "1")
    assert manifest.is_strict() is True


# ---------- the pose model's contract and the GPU ----------


@pytest.mark.parametrize(
    "session,what",
    [
        (FakeSession(inputs=[Port("input", [1, 3, 256, 192])]), "input"),  # a smaller RTMPose
        (FakeSession(inputs=[Port("a", [1, 3, 384, 288]), Port("b", [1])]), "input"),
        (
            FakeSession(outputs=[Port("simcc_x", [1, 17, 576]), Port("simcc_y", [1, 17, 768])]),
            "simcc_x",
        ),  # body-only model
        (
            FakeSession(outputs=[Port("simcc_x", [1, 133, 384]), Port("simcc_y", [1, 133, 512])]),
            "simcc_x",
        ),  # other input size
        (FakeSession(outputs=[Port("output", [1, 133, 3])]), "simcc_x"),  # not a SimCC head
    ],
)
def test_a_pose_model_with_the_wrong_inputs_or_outputs_is_refused(tmp_path, session, what):
    with pytest.raises(ModelError) as e:
        manifest.check_onnx_io(session)
    assert e.value.code == "model_incompatible" and what in e.value.message
    report = check(install(tmp_path), load=lambda *a: FakeLoaded(session))
    assert not report.ok and report.error_code == "model_incompatible"


def test_a_symbolic_batch_size_is_accepted():
    session = FakeSession(
        inputs=[Port("input", ["batch", 3, 384, 288])],
        outputs=[Port("simcc_x", ["batch", 133, 576]), Port("simcc_y", ["batch", 133, 768])],
    )
    assert manifest.check_onnx_io(session)["input"] == "input"


def test_a_gpu_that_was_asked_for_but_is_not_in_use_is_an_error_not_a_slow_run(tmp_path):
    cpu_only = FakeLoaded(FakeSession(providers=["CPUExecutionProvider"]))
    report = check(install(tmp_path), device="cuda", load=lambda *a: cpu_only)
    assert (
        not report.ok
        and report.error_code == "gpu_unavailable"
        and "CPUExecutionProvider" in report.error
    )
    on_gpu = FakeLoaded(FakeSession(providers=["CUDAExecutionProvider", "CPUExecutionProvider"]))
    assert (
        check(install(tmp_path), device="cuda", load=lambda *a: on_gpu).providers[0]
        == "CUDAExecutionProvider"
    )
    assert check(
        install(tmp_path), device="cpu", load=lambda *a: cpu_only
    ).ok  # CPU asked, CPU used


@pytest.mark.parametrize(
    "failure,code",
    [
        (ImportError("No module named 'ultralytics'"), "pose_dependencies_missing"),
        (ImportError("No module named 'onnxruntime'"), "pose_dependencies_missing"),
        (RuntimeError("CUDA out of memory at /secret/path"), "model_load_failed"),
        (OSError("libcudnn.so.9: cannot open shared object file"), "model_load_failed"),
    ],
)
def test_missing_gpu_libraries_and_load_failures_are_reported_without_internals(
    tmp_path, failure, code
):
    def load(*a):
        raise failure

    report = check(install(tmp_path), load=load)
    assert not report.ok and report.error_code == code
    assert "/secret/path" not in report.error and "libcudnn" not in report.error


def test_a_model_that_loads_but_cannot_run_a_frame_fails_the_check(tmp_path):
    report = check(
        install(tmp_path), load=lambda *a: FakeLoaded(smoke_error=RuntimeError("bad op"))
    )
    assert (
        not report.ok
        and report.error_code == "model_load_failed"
        and report.smoke_test == "not run"
    )


# ---------- the local source ----------


def test_the_local_source_refuses_to_download_weights_at_run_time(monkeypatch, tmp_path):
    monkeypatch.setattr(rtmw_backend, "MODELS_DIR", tmp_path)
    with pytest.raises(FileNotFoundError, match="not installed"):
        rtmw_backend.YoloPersonDetector.from_config(ModelConfig(), offline=True)


def test_a_broken_worker_image_fails_the_job_once_and_does_not_blame_the_video(
    monkeypatch, tmp_path, swim_video
):
    monkeypatch.setattr(rtmw_backend, "MODELS_DIR", install(tmp_path))
    (tmp_path / "rtmw_x_stock.onnx").write_bytes(b"tampered with")
    monkeypatch.setenv("AQUATRACK_MODELS_STRICT", "1")
    with pytest.raises(PoseSourceError) as e:
        LocalModelPoseSource(ModelConfig()).get_raw_pose(
            swim_video, video_identity(swim_video), "v"
        )
    assert e.value.code == "model_checksum_mismatch" and e.value.retryable is False
    assert "Nothing is wrong with your video" in e.value.message


def test_a_verified_local_run_records_which_files_and_versions_produced_the_pose(
    monkeypatch, tmp_path, swim_video
):
    """FAKE estimator; what is checked is the bookkeeping around it."""
    monkeypatch.setattr(rtmw_backend, "MODELS_DIR", install(tmp_path))
    monkeypatch.setenv("AQUATRACK_MODELS_STRICT", "1")
    monkeypatch.setenv("AQUATRACK_POSE_DEVICE", "cuda")
    seen = {}

    class FakeEstimator:
        def estimate_raw(self, path, config, video_id, source, produced_by, on_frame):
            seen.update(source=source, produced_by=produced_by)
            on_frame(1, 250)
            return make_raw_pose(swim_video)

    loaded = FakeLoaded(FakeSession(providers=["CUDAExecutionProvider"]))
    loaded.estimator = FakeEstimator()
    src = LocalModelPoseSource(ModelConfig())
    monkeypatch.setattr(src, "_build", lambda *a: loaded)
    monkeypatch.setattr(
        src, "_library_versions", lambda: {"ultralytics": "8.4.210", "onnxruntime-gpu": "1.22.0"}
    )
    ticks = []
    raw = src.get_raw_pose(
        swim_video, video_identity(swim_video), "v", progress=lambda d, t: ticks.append((d, t))
    )
    assert src.device == "cuda" and seen == {"source": "local", "produced_by": "worker"}
    assert raw.meta.detector.sha256 == manifest.sha256_of(tmp_path / "yolo11m.pt")
    assert raw.meta.detector.version == "ultralytics 8.4.210"
    assert raw.meta.pose.version == "onnxruntime 1.22.0 on cuda" and ticks == [(1, 250)]


def test_known_model_sources_are_public_publisher_urls_never_a_drive_or_colab():
    for source in manifest.SOURCES.values():
        assert source.url.startswith(
            ("https://github.com/ultralytics/", "https://download.openmmlab.com/")
        )
    text = " ".join(
        Path(p).read_text()
        for p in (
            "src/aquatrack/analysis/pose/manifest.py",
            "src/aquatrack/analysis/pose/rtmw_backend.py",
            "src/aquatrack/analysis/pose/sources.py",
            "scripts/fetch_models.py",
            "scripts/export_rtmw_onnx.py",
            "worker/Dockerfile",
        )
    )
    assert "drive.google" not in text and "MyDrive" not in text and "colab.research" not in text
    assert (
        manifest.SOURCES["yolo11m.pt"].sha256 is None
    )  # not published; pinned at the first build, never guessed


def test_fetch_and_export_scripts_refuse_to_run_without_the_owners_acceptance(tmp_path):
    import subprocess
    import sys

    for script, args in (
        ("scripts/fetch_models.py", ["--models-dir", str(tmp_path)]),
        ("scripts/export_rtmw_onnx.py", ["--out", str(tmp_path / "x.onnx")]),
    ):
        run = subprocess.run([sys.executable, script, *args], capture_output=True, text=True)
        assert run.returncode == 2 and "MODEL_LICENSING_DECISION" in run.stderr
    assert list(tmp_path.iterdir()) == []  # nothing was downloaded or written


# ---------- stopping a running inference ----------


class SlowInference(FakeInference):
    """FAKE pose source that reports frame by frame, like the real estimator does."""

    supports_progress = True

    def __init__(self, swim_video, at_frame=None, frames=200):
        super().__init__(swim_video)
        self.at_frame, self.frames, self.reached = at_frame or {}, frames, 0

    def get_raw_pose(self, video_path, video, video_id, progress=None):
        for done in range(1, self.frames + 1):
            if done in self.at_frame:
                self.at_frame[done]()
            self.reached = done
            progress(done, self.frames)
        return make_raw_pose(self.video)


@pytest.fixture
def store(swim_video, monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "PROGRESS_EVERY_S", 0.0)  # look for a reason to stop at every frame
    monkeypatch.setenv("AQUATRACK_TMP_DIR", str(tmp_path / "work"))
    (tmp_path / "work").mkdir()
    s = MemoryStore()
    add_video(s, swim_video)
    request_analysis(s, "vid1", UID)
    return s


def left_behind(tmp_path) -> list:
    return list((tmp_path / "work").iterdir())


def test_a_cancel_stops_the_inference_within_frames_not_at_the_end(store, swim_video, tmp_path):
    source = SlowInference(swim_video, {40: lambda: cancel_analysis(store, "vid1", UID)})
    run_job(store, source, "vid1")
    assert source.reached <= 41  # stopped where it was, with 160 frames still to go
    assert status(store) == "canceled" and not store.analyses
    assert not [f for f in store.files if f.startswith("analysis/")]
    assert left_behind(tmp_path) == []  # the downloaded video is gone too


def test_deleting_the_video_stops_the_inference_and_leaves_nothing_anywhere(
    store, swim_video, tmp_path
):
    source = SlowInference(swim_video, {30: lambda: jobs.delete_video(store, "vid1", UID)})
    run_job(store, source, "vid1")
    assert source.reached <= 31 and "vid1" not in store.videos
    assert not store.analyses and not [f for f in store.files if "vid1" in f]
    assert left_behind(tmp_path) == []


def test_an_inference_that_runs_past_the_time_limit_is_stopped_mid_way(
    store, swim_video, monkeypatch, tmp_path
):
    source = SlowInference(swim_video, {50: lambda: monkeypatch.setattr(jobs, "JOB_TIMEOUT_S", -1)})
    run_job(store, source, "vid1")
    assert source.reached <= 51 and (status(store), job(store)["errorCode"]) == (
        "failed",
        "timeout",
    )
    assert job(store)["retryable"] is True and left_behind(tmp_path) == []


def test_a_worker_that_lost_its_lease_mid_inference_stops_and_stores_nothing(
    store, swim_video, tmp_path
):
    def taken_over():
        store.videos["vid1"]["job"]["leaseOwner"] = "another-worker"

    source = SlowInference(swim_video, {60: taken_over})
    run_job(store, source, "vid1", worker_id="first")
    assert source.reached <= 61 and status(store) == "analyzing"  # the new owner carries on
    assert job(store)["leaseOwner"] == "another-worker" and not store.analyses


def test_progress_is_reported_while_frames_are_processed(store, swim_video):
    seen = []
    source = SlowInference(swim_video, {120: lambda: seen.append(dict(job(store)["progress"]))})
    run_job(store, source, "vid1")
    assert seen[0]["stage"] == "pose" and seen[0]["done"] == 119 and seen[0]["total"] == 200
    assert status(store) == "ready" and job(store)["progress"] is None


def test_a_job_that_outgrows_the_memory_limit_fails_with_a_reason(
    store, swim_video, monkeypatch, tmp_path
):
    monkeypatch.setattr(jobs, "MAX_RSS_MB", 100)
    monkeypatch.setattr(jobs, "rss_mb", lambda: 5000.0)
    source = SlowInference(swim_video)
    run_job(store, source, "vid1")
    assert source.reached == 25  # checked every 25 frames
    assert (status(store), job(store)["errorCode"], job(store)["retryable"]) == (
        "failed",
        "worker_memory",
        False,
    )
    assert "more memory" in job(store)["errorMessage"] and left_behind(tmp_path) == []


def test_a_result_that_was_only_partly_stored_is_removed_when_the_save_fails(
    store, swim_video, monkeypatch, tmp_path
):
    def half_saved(video, analysis_id, result, files):
        store.files[f"analysis/{UID}/vid1/{analysis_id}/raw_pose.npz"] = (
            b"pose bytes"  # one file made it
        )
        raise ConnectionError("storage went away")

    monkeypatch.setattr(store, "save_analysis", half_saved)
    run_job(store, FakeInference(swim_video), "vid1")
    assert status(store) == "failed" and job(store)["retryable"] is True
    assert not [f for f in store.files if f.startswith("analysis/")]  # no orphaned pose data
    assert not store.analyses and left_behind(tmp_path) == []


def test_working_files_of_a_killed_worker_are_removed_when_the_next_one_starts(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("AQUATRACK_TMP_DIR", str(tmp_path))
    stale = tmp_path / "aquatrack-job-killed"
    stale.mkdir()
    (stale / "video.mp4").write_bytes(b"a swimmer's video")
    (tmp_path / "unrelated").mkdir()
    assert jobs.clean_work_dirs(older_than_s=3600) == 0  # could belong to a job still running
    assert jobs.clean_work_dirs(older_than_s=0) == 1
    assert not stale.exists() and (tmp_path / "unrelated").exists()


# ---------- worker start-up ----------


class Unready:
    """FAKE source whose model check fails, like a worker image with a bad model file."""

    name = "local"

    def preflight(self):
        return manifest.Preflight(
            ok=False,
            error_code="model_checksum_mismatch",
            error="rtmw_x_stock.onnx does not match the checksum in the manifest.",
        )


def test_a_worker_whose_models_fail_the_check_exits_before_it_claims_anything(
    store, monkeypatch, capsys
):
    monkeypatch.setattr(worker, "pose_source_from_env", lambda cfg: Unready())
    monkeypatch.setenv("AQUATRACK_ENV", "test")
    assert worker.main(["--drain"], store_factory=lambda: store) == 3
    assert status(store) == "queued" and job(store)["attempts"] == 1  # the job is untouched
    assert "model check failed: model_checksum_mismatch" in capsys.readouterr().err


def test_check_mode_reports_and_exits_without_touching_the_queue(
    store, swim_video, monkeypatch, capsys
):
    monkeypatch.setattr(worker, "pose_source_from_env", lambda cfg: FakeInference(swim_video))
    monkeypatch.setenv("AQUATRACK_ENV", "test")
    assert (
        worker.main(["--check"], store_factory=lambda: pytest.fail("the store must not be opened"))
        == 0
    )
    assert "configuration is usable" in capsys.readouterr().out and status(store) == "queued"


def test_a_worker_with_an_unsafe_configuration_does_not_start(monkeypatch, capsys):
    for name in ("FIRESTORE_EMULATOR_HOST", "STORAGE_EMULATOR_HOST", "FIREBASE_AUTH_EMULATOR_HOST"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AQUATRACK_ENV", "production")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "aquatrack-live")
    monkeypatch.setenv("AQUATRACK_ALLOW_PRODUCTION_FIREBASE", "1")
    monkeypatch.setenv("AQUATRACK_POSE_SOURCE", "precomputed")
    assert worker.main(["--once"], store_factory=lambda: pytest.fail("must not start")) == 2
    assert "development fixture" in capsys.readouterr().err
    monkeypatch.setenv("AQUATRACK_POSE_SOURCE", "telepathy")
    monkeypatch.setenv("AQUATRACK_ENV", "test")
    assert worker.main(["--once"], store_factory=lambda: pytest.fail("must not start")) == 2


def test_drain_mode_works_through_the_queue_and_exits_so_no_gpu_idles(
    store, swim_video, monkeypatch
):
    add_video(store, swim_video, "vid2", uid="swimmer-2")
    request_analysis(store, "vid2", "swimmer-2")
    w = Worker(store, FakeInference(swim_video), "drain")
    assert w.run_forever(poll_s=60, drain=True) == 2  # returns at once when the queue is empty
    assert status(store) == status(store, "vid2") == "ready"
    assert w.run_forever(poll_s=60, drain=True) == 0
    request_analysis(store, "vid1", UID, rerun=True)
    request_analysis(store, "vid2", "swimmer-2", rerun=True)
    assert (
        Worker(store, FakeInference(swim_video), "capped").run_forever(poll_s=60, max_jobs=1) == 1
    )


# ---------- the comparison the acceptance test uses (synthetic pose) ----------


def shifted(raw, px=0.0, score=0.0, drop=0):
    """A copy of a SYNTHETIC pose run with its points, scores or boxes changed."""
    import copy

    other = copy.deepcopy(raw)
    other.keypoints[..., 0] += px / raw.meta.width
    other.keypoints[..., 2] += score
    if drop:
        other.boxes[:drop] = np.nan
    return other


def test_two_runs_of_the_same_video_are_compared_and_small_runtime_differences_pass(swim_video):
    reference = make_raw_pose(swim_video)
    new = shifted(reference, px=1.0)  # a pixel of difference, as between two runtimes
    new.meta.pose.sha256, new.meta.pose.version = "b" * 64, "onnxruntime 1.22.0 on cuda"
    out = compare_raw_pose(new, reference)
    assert out.comparable and out.within_tolerance and out.differences == []
    assert out.body_px_median == pytest.approx(1.0, abs=0.01) and out.box_iou_median == 1.0
    assert any("Different ONNX export" in c for c in out.context)  # stated, not hidden
    assert any("Pose runtime" in c for c in out.context)


@pytest.mark.parametrize(
    "change,expected",
    [
        (dict(px=25.0), "Median joint distance"),
        (dict(score=-4.0), "different model generation"),  # e.g. the cocktail13 model's score scale
        (dict(drop=60), "Frames with a swimmer box"),
    ],
)
def test_real_differences_are_reported_not_averaged_away(swim_video, change, expected):
    reference = make_raw_pose(swim_video)
    out = compare_raw_pose(shifted(reference, **change), reference)
    assert out.comparable and not out.within_tolerance
    assert any(expected in d for d in out.differences), out.differences


def test_runs_of_different_videos_or_sampling_are_not_compared_at_all(swim_video):
    reference = make_raw_pose(swim_video)
    other = shifted(reference)
    other.meta.video = other.meta.video.model_copy(update={"sha256": "c" * 64})
    out = compare_raw_pose(other, reference)
    assert (
        not out.comparable
        and "different video files" in out.reasons[0]
        and out.body_px_median is None
    )
    assert Tolerances().body_px_median == 3.0  # the tolerances are stated, in one place


def test_metrics_are_compared_one_by_one_with_status_changes_flagged():
    ref = [
        {"key": "stroke_rate", "value": 23.9, "status": "reliable"},
        {"key": "body_line_angle", "value": 8.4, "status": "reliable"},
        {"key": "head_height", "value": 0.0, "status": "reliable"},
    ]
    new = [
        {"key": "stroke_rate", "value": 24.0, "status": "reliable"},
        {"key": "body_line_angle", "value": 11.0, "status": "reliable"},
        {"key": "head_height", "value": 0.0, "status": "limited"},
        {"key": "new_metric", "value": 1.0, "status": "reliable"},
    ]
    rows = {r["key"]: r.get("flag") for r in compare_metrics(new, ref)}
    assert rows == {
        "stroke_rate": "",
        "body_line_angle": "value moved by +2.600",
        "head_height": "status reliable -> limited",
        "new_metric": "only in the new run",
    }


@pytest.mark.parametrize("absolute", [True, False])
def test_the_worker_finds_the_detector_file_it_has_just_verified(monkeypatch, tmp_path, absolute):
    """Found by the first real run (2026-11-27). The worker hands the detector the path of
    the file it checked against the manifest. `from_config` only looked up bare file names in
    the models folder, so that path, absolute in the image and relative locally, was
    reported as "not installed" and no model could ever load. Not caught earlier because
    every earlier test used a fake detector."""
    models = tmp_path / "models"
    models.mkdir()
    (models / "yolo11m.pt").write_bytes(b"weights")
    monkeypatch.setattr(rtmw_backend, "MODELS_DIR", models)
    monkeypatch.chdir(tmp_path)
    opened = []
    monkeypatch.setattr(
        rtmw_backend.YoloPersonDetector,
        "__init__",
        lambda self, weights, **kwargs: opened.append(Path(weights)),
    )
    given = models / "yolo11m.pt" if absolute else Path("models") / "yolo11m.pt"
    config = ModelConfig(detector_weights=str(given))
    rtmw_backend.YoloPersonDetector.from_config(config, offline=True)
    assert opened and opened[0].resolve() == (models / "yolo11m.pt").resolve()
    # a bare name is still looked up in the models folder, and a missing file is still refused
    rtmw_backend.YoloPersonDetector.from_config(
        ModelConfig(detector_weights="yolo11m.pt"), offline=True
    )
    assert opened[-1] == models / "yolo11m.pt"
    with pytest.raises(FileNotFoundError):
        rtmw_backend.YoloPersonDetector.from_config(
            ModelConfig(detector_weights="other.pt"), offline=True
        )
