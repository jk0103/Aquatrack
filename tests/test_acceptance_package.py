"""The Phase 9B execution package, checked as far as it can be without a build, a GPU or a
download: the scripts' arguments and exit codes, the download checks, the export script's
configuration, the build context, and the files the container and job are made from.

Test kinds in this file: pure unit tests and MOCKED model inference (a fake pose source
returning a synthetic swimmer). Nothing here runs YOLO11m or RTMW-x. "real_inference" in a
report is asserted to be False whenever a fake source was used, so a mocked run can never be
mistaken for the real one."""
# ruff: noqa: E501

import copy
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest
from conftest import make_raw_pose
from test_inference_worker import FakeLoaded, FakeSession

from aquatrack.analysis.pose import manifest
from aquatrack.analysis.pose.manifest import ModelError, ModelSource
from aquatrack.analysis.video import video_identity

ROOT = Path(__file__).resolve().parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


acceptance = script("gpu_acceptance")
compare_pose = script("compare_pose")
export = script("export_rtmw_onnx")


class MockSource:
    """MOCKED pose source: a synthetic swimmer, no model. Shaped like LocalModelPoseSource."""

    def __init__(
        self,
        swim_video,
        device="cuda",
        providers=("CUDAExecutionProvider", "CPUExecutionProvider"),
        ok=True,
        shift_px=0.0,
    ):
        self.video, self.device, self.shift_px = swim_video, device, shift_px
        self.report = manifest.Preflight(
            ok=ok,
            device=device,
            strict=True,
            providers=list(providers),
            files=[{"name": "yolo11m.pt", "sha256": "a" * 64, "bytes": 1, "verified": True}],
            error_code="" if ok else "model_checksum_mismatch",
            error="" if ok else "rtmw_x_stock.onnx does not match the checksum in the manifest.",
        )

    def preflight(self):
        return self.report

    def get_raw_pose(self, video_path, video, video_id, progress=None):
        raw = make_raw_pose(self.video)
        raw.keypoints[..., 0] += self.shift_px / raw.meta.width
        raw.meta.detector.sha256, raw.meta.pose.sha256 = "a" * 64, "b" * 64
        progress(50, 250)
        return raw


def run_acceptance(tmp_path, swim_video, source, *extra):
    out = tmp_path / "out"
    code = acceptance.main(
        ["--video", str(swim_video), "--out-dir", str(out), *extra], source=source
    )
    return code, json.loads((out / "acceptance.json").read_text()), out


# ---------- the acceptance script (mocked inference) ----------


def test_a_mocked_run_writes_the_report_and_a_pose_file_named_like_the_reference(
    tmp_path, swim_video, capsys
):
    sha = video_identity(swim_video).sha256
    code, report, out = run_acceptance(
        tmp_path, swim_video, MockSource(swim_video), "--video-sha256", sha
    )
    assert code == 0 and report["exit_status"] == 0
    assert report["real_inference"] is False  # a fake source can never be reported as real
    assert (
        report["video"]["sha256"] == sha and report["artifacts"]["raw_pose"] == f"{sha}.rawpose.npz"
    )
    assert (out / f"{sha}.rawpose.npz").exists()
    assert report["run"]["frames"] == 250 and report["run"]["device"] == "cuda"
    assert (
        report["models"]["detector"]["sha256"] == "a" * 64
        and report["models"]["pose"]["sha256"] == "b" * 64
    )
    assert report["preflight"]["providers"][0] == "CUDAExecutionProvider"
    assert report["analysis"]["grade"] == "good" and "stroke_rate" in report["analysis"]["metrics"]
    assert "compare_pose.py" in report["verdict"]
    line = next(
        x for x in capsys.readouterr().out.splitlines() if x.startswith("ACCEPTANCE_REPORT ")
    )
    assert (
        json.loads(line.removeprefix("ACCEPTANCE_REPORT "))["video"]["sha256"] == sha
    )  # readable from a log


def test_exit_3_when_the_models_fail_their_check_and_nothing_is_processed(tmp_path, swim_video):
    code, report, out = run_acceptance(tmp_path, swim_video, MockSource(swim_video, ok=False))
    assert code == 3 and report["preflight"]["error_code"] == "model_checksum_mismatch"
    assert "run" not in report and not list(out.glob("*.npz"))


def test_exit_5_when_a_gpu_was_asked_for_and_the_run_would_be_on_the_cpu(tmp_path, swim_video):
    cpu = MockSource(swim_video, device="cuda", providers=("CPUExecutionProvider",))
    code, report, out = run_acceptance(tmp_path, swim_video, cpu)
    assert code == 5 and "GPU" in report["error"] and not list(out.glob("*.npz"))


def test_exit_4_when_the_video_is_not_the_expected_file(tmp_path, swim_video):
    code, report, out = run_acceptance(
        tmp_path, swim_video, MockSource(swim_video), "--video-sha256", "0" * 64
    )
    assert code == 4 and "SHA-256 differs" in report["error"] and "preflight" not in report


def test_exit_4_when_the_video_cannot_be_downloaded(tmp_path, swim_video, monkeypatch):
    def offline(*a, **k):
        raise OSError("no network in tests")

    monkeypatch.setattr(acceptance.urllib.request, "urlopen", offline)
    out = tmp_path / "out"
    code = acceptance.main(
        [
            "--video-url",
            "https://example.org/x.webm",
            "--video-sha256",
            "0" * 64,
            "--out-dir",
            str(out),
        ],
        source=MockSource(swim_video),
    )
    assert (
        code == 4
        and "download failed" in json.loads((out / "acceptance.json").read_text())["error"]
    )
    with pytest.raises(SystemExit):  # a URL without the hash it must have is refused outright
        acceptance.main(["--video-url", "https://example.org/x.webm", "--out-dir", str(out)])


def test_with_a_reference_the_verdict_is_within_tolerance_or_differences_never_silent(
    tmp_path, swim_video
):
    reference = tmp_path / "reference.rawpose.npz"
    make_raw_pose(swim_video).save(reference)
    code, report, _ = run_acceptance(
        tmp_path, swim_video, MockSource(swim_video, shift_px=1.0), "--reference", str(reference)
    )
    assert (
        code == 0
        and report["verdict"] == "within tolerance"
        and report["tolerances"]["body_px_median"] == 3.0
    )
    code, report, _ = run_acceptance(
        tmp_path, swim_video, MockSource(swim_video, shift_px=40.0), "--reference", str(reference)
    )
    assert code == 1 and report["verdict"] == "differences to explain"
    assert any("Median joint distance" in d for d in report["pose_comparison"]["differences"])


def test_the_real_entry_point_is_the_local_model_source_and_fails_cleanly_without_models(
    tmp_path, swim_video, monkeypatch
):
    """No source is injected, as in a real run. On this machine there are no model files,
    so the honest outcome is exit 3 with real_inference still marked true-by-construction."""
    from aquatrack.analysis.pose import rtmw_backend

    monkeypatch.setattr(rtmw_backend, "MODELS_DIR", tmp_path / "no-models")
    monkeypatch.setenv("AQUATRACK_MODELS_STRICT", "1")
    out = tmp_path / "out"
    code = acceptance.main(["--video", str(swim_video), "--out-dir", str(out)])
    report = json.loads((out / "acceptance.json").read_text())
    assert code == 3 and report["real_inference"] is True and report["preflight"]["ok"] is False
    assert report["preflight"]["error_code"] == "model_manifest_missing" and "run" not in report


# ---------- comparing afterwards, without models ----------


def test_compare_pose_reports_within_tolerance_differences_and_refuses_another_video(
    tmp_path, swim_video, sample_video, capsys
):
    reference, new, far = tmp_path / "ref.npz", tmp_path / "new.npz", tmp_path / "far.npz"
    raw = make_raw_pose(swim_video)
    raw.save(reference)
    close = copy.deepcopy(raw)
    close.keypoints[..., 0] += 1.0 / raw.meta.width
    close.save(new)
    moved = copy.deepcopy(raw)
    moved.keypoints[..., 0] += 60.0 / raw.meta.width
    moved.save(far)
    args = ["--reference", str(reference), "--video", str(swim_video)]
    assert compare_pose.main(["--new", str(new), *args, "--out", str(tmp_path / "r.json")]) == 0
    assert json.loads((tmp_path / "r.json").read_text())["verdict"] == "within tolerance"
    assert compare_pose.main(["--new", str(far), *args]) == 1
    from aquatrack.analysis.pose.sources import PoseSourceError

    with pytest.raises(PoseSourceError):  # a pose file of some other video is not compared at all
        compare_pose.main(
            ["--new", str(new), "--reference", str(reference), "--video", str(sample_video)]
        )


# ---------- downloads and the export configuration ----------


def test_a_download_is_checked_against_everything_its_publisher_states(tmp_path):
    data = b"stand-in bytes, not a model"
    path = tmp_path / "file-ab12cd34.pth"
    path.write_bytes(data)
    sha, md5 = hashlib.sha256(data).hexdigest(), hashlib.md5(data).hexdigest()
    good = ModelSource(
        name=path.name,
        role="x",
        url="https://x",
        publisher="x",
        bytes=len(data),
        md5=md5,
        sha256_prefix=sha[:8],
        sha256=sha,
    )
    assert manifest.check_download(path, good) == sha
    for change in (
        dict(bytes=len(data) + 1),
        dict(md5="0" * 32),
        dict(sha256_prefix="deadbeef"),
        dict(sha256="f" * 64),
    ):
        with pytest.raises(ModelError) as e:
            manifest.check_download(path, ModelSource(**(good.__dict__ | change)))
        assert e.value.code == "model_download_mismatch" and str(tmp_path) not in e.value.message


def test_the_known_sources_carry_what_was_read_from_the_publishers_servers():
    yolo = manifest.SOURCES["yolo11m.pt"]
    pth = manifest.SOURCES["rtmw-x_simcc-cocktail14_pt-ucoco_270e-384x288-f840f204_20231122.pth"]
    assert (yolo.bytes, yolo.sha256) == (
        40_684_120,
        None,
    )  # size from the release; no hash is published
    assert (pth.bytes, pth.md5, pth.sha256_prefix) == (
        369_720_404,
        "e80606e7db921ddc566f8eb7a2ec119f",
        "f840f204",
    )
    assert pth.sha256_prefix in pth.name and "cocktail14" in pth.name and "384x288" in pth.name


def test_the_export_is_configured_for_exactly_the_contract_the_worker_checks():
    info = export.self_check()
    contract = manifest.OnnxContract()
    assert tuple(info["input"]) == contract.input_shape and info["outputs"] == [
        n for n, _ in contract.outputs
    ]
    assert info["opset"] == 17 and "rtmw-x_8xb320-270e_cocktail14-384x288" in info["config"]
    # width 288 and height 384 give SimCC bins of twice each: what the estimator decodes
    assert dict(contract.outputs) == {"simcc_x": (1, 133, 288 * 2), "simcc_y": (1, 133, 384 * 2)}


def test_the_mmpose_import_patches_apply_once_and_change_nothing_else(tmp_path):
    heads = tmp_path / "models" / "heads"
    transforms = tmp_path / "datasets" / "transforms"
    heads.mkdir(parents=True)
    transforms.mkdir(parents=True)
    (heads / "__init__.py").write_text(
        "from .a import A\nfrom .transformer_heads import EDPoseHead\n__all__ = ['A']\n"
    )
    (transforms / "common_transforms.py").write_text(
        "x = getattr(albumentations.augmentations.transforms, obj_type)\n"
    )
    assert export.patch_mmpose(tmp_path) == [
        "models/heads/__init__.py",
        "datasets/transforms/common_transforms.py",
    ]
    text = (heads / "__init__.py").read_text()
    assert "except ImportError:\n    EDPoseHead = None" in text and "from .a import A" in text
    assert (
        transforms / "common_transforms.py"
    ).read_text() == "x = getattr(albumentations, obj_type)\n"
    assert export.patch_mmpose(tmp_path) == []  # running it again does nothing


# ---------- what goes into the build ----------


@pytest.mark.parametrize("name", [".dockerignore", ".gcloudignore"])
def test_the_build_context_is_an_allowlist_that_cannot_carry_private_files(name):
    lines = [
        x.strip()
        for x in (ROOT / name).read_text().splitlines()
        if x.strip() and not x.startswith("#")
    ]
    assert lines[0] == "*"  # everything is ignored first
    allowed = {x[1:] for x in lines if x.startswith("!")}
    assert allowed == {
        "pyproject.toml",
        "uv.lock",
        "README.md",
        "src/",
        "src/**",
        "scripts/",
        "scripts/**",
        "worker/",
        "worker/**",
    }
    for private in (
        "data",
        "experiments",
        "test_videos",
        "docs",
        "frontend",
        "models",
        ".env",
        "tests",
        "firebase",
        ".git",
    ):
        assert not any(a.startswith(private) for a in allowed), private


def dockerfile() -> str:
    return (ROOT / "worker" / "Dockerfile").read_text()


def test_the_dockerfile_refuses_to_build_without_acceptance_and_holds_no_secrets_or_weights():
    text = dockerfile()
    assert (
        text.count('test "$ACCEPT_MODEL_TERMS" = "yes"') >= 1
        and "ARG ACCEPT_MODEL_TERMS=no" in text
    )
    assert "--accept-model-terms" in text  # the scripts' own gate is passed explicitly
    assert not re.search(r"(?i)(api[_-]?key|secret|password|token)\s*=", text)
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in text and "drive.google" not in text
    assert "COPY --from=export /models /models" in text  # weights come from the build stage only
    assert not re.search(r"COPY .*\.(pt|pth|onnx)\b", text)
    assert "USER worker" in text and "useradd" in text  # not root
    for setting in (
        "AQUATRACK_MODELS_STRICT=1",
        "AQUATRACK_POSE_SOURCE=local",
        "AQUATRACK_POSE_DEVICE=cuda",
        "AQUATRACK_MODELS_DIR=/models",
    ):
        assert setting in text
    assert "python -m aquatrack.worker --check" in text  # the image checks itself while building
    assert 'ENTRYPOINT ["python", "-m", "aquatrack.worker"]' in text and '"--drain"' in text


def test_the_dockerfile_copies_only_what_the_build_context_allows():
    copied = set(re.findall(r"^COPY (?!--from)(.+?) \S+$", dockerfile(), flags=re.M))
    names = {part for group in copied for part in group.split()}
    assert names <= {"pyproject.toml", "uv.lock", "README.md", "src", "scripts"}, names


def test_the_test_script_bounds_every_paid_step_and_refuses_without_a_project():
    text = (ROOT / "worker" / "phase9b.sh").read_text()
    for bound in (
        "--tasks 1",
        "--parallelism 1",
        "--max-retries 0",
        '--task-timeout "${TASK_TIMEOUT}"',
        'TASK_TIMEOUT="15m"',
        "--gpu 1 --gpu-type nvidia-l4 --no-gpu-zonal-redundancy",
        "--cpu 4 --memory 16Gi",
        'REGION="us-central1"',
        "MAX_EXECUTIONS=5",
    ):
        assert bound in text, bound
    assert "set -euo pipefail" in text and ': "${PROJECT_ID:?' in text
    assert (
        'ACCEPT_MODEL_TERMS:-no}" = "yes"' in text
    )  # nothing builds without the owner's acceptance
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in text and "key.json" not in text  # no key files
    assert (
        "ce32d556ba1399b9dd5000f9a079475ca33377a9280cf30619a566ff8e9523c3" in text
    )  # the public clip, by hash
    assert (
        "upload.wikimedia.org" in text and "firebase" not in text.lower()
    )  # no Firebase, no user data
    for step in (
        "check)",
        "setup)",
        "build)",
        "create)",
        "run)",
        "status)",
        "fetch)",
        "stop)",
        "cleanup)",
        "verify)",
    ):
        assert step in text, step
    import subprocess

    assert (
        subprocess.run(["bash", "-n", str(ROOT / "worker" / "phase9b.sh")]).returncode == 0
    )  # it parses
    run = subprocess.run(
        ["bash", str(ROOT / "worker" / "phase9b.sh"), "run"],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert run.returncode != 0 and "PROJECT_ID" in run.stderr  # no project named: it does nothing


def test_the_build_is_bounded_and_one_cuda_version_is_used_throughout():
    build = (ROOT / "worker" / "cloudbuild.yaml").read_text()
    assert (
        "timeout: 2700s" in build
        and '_ACCEPT: "no"' in build
        and "ACCEPT_MODEL_TERMS=${_ACCEPT}" in build
    )
    text = dockerfile()
    assert (
        "nvidia/cuda" not in text.split("# ---- stage 1")[1]
    )  # no CUDA base image to disagree with the wheels
    assert '"onnxruntime-gpu>=1.30,<1.31"' in text  # a release documented as built for CUDA 13.0
    assert (
        "uv sync --locked --no-dev --extra pose" in text
    )  # the locked versions, not whatever is newest
    lock = (ROOT / "uv.lock").read_text()
    assert (
        'name = "nvidia-cudnn-cu13"' in lock and 'name = "nvidia-cudnn-cu12"' not in lock
    )  # PyTorch brings CUDA 13
    assert re.search(
        r'name = "ultralytics"\nversion = "8\.4\.210"', lock
    )  # the version behind the reference pose
    assert (
        '"numpy<2"' in text and "torch==2.5.1" in text
    )  # the export tool chain is pinned apart from the worker


def test_every_script_documents_how_it_refuses_and_none_runs_on_import():
    for name in ("fetch_models", "export_rtmw_onnx", "gpu_acceptance", "compare_pose"):
        text = (ROOT / "scripts" / f"{name}.py").read_text()
        assert 'if __name__ == "__main__":' in text and "raise SystemExit(main())" in text
    assert "--accept-model-terms" in (ROOT / "scripts" / "fetch_models.py").read_text()
    assert sys.version_info >= (3, 11)


def test_fake_onnx_fixtures_used_by_these_tests_are_not_model_files():
    assert (
        FakeLoaded(FakeSession()).smoke().startswith("ran on a blank frame")
    )  # a stand-in, by name and by size
