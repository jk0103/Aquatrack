"""Which model files the inference worker may load, where they come from, and the checks
that run before any video is touched.

No weights are in this repository. A worker image gets them at build time from their
public sources (`scripts/fetch_models.py`, `scripts/export_rtmw_onnx.py`) and writes
`manifest.json` next to them with each file's size and SHA-256. At start the worker checks
the files against that manifest, checks the ONNX model's inputs and outputs, and, when a GPU
was asked for, that inference really runs on it. A worker that fails any of this stops
before it claims a job, so a broken image can never use up a swimmer's attempts.

Nothing here downloads anything, and nothing reads from a personal Drive or Colab session.
See docs/INFERENCE_WORKER.md and docs/MODEL_LICENSING_DECISION.md (the licences of these
weights are not settled; fetching them is a decision for the owner).
"""

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

MANIFEST_NAME = "manifest.json"
NUM_KEYPOINTS = 133


@dataclass(frozen=True)
class ModelSource:
    """A model file as its publisher distributes it."""

    name: str
    role: str
    url: str
    publisher: str
    bytes: int | None = None
    sha256: str | None = None  # the full hash, when one is known
    sha256_prefix: str | None = None  # what the publisher's file name promises
    note: str = ""


# The baseline chosen in Phase 1 (docs/POSE_PROCESSING.md). Sizes and hashes below are what
# has actually been observed; "None" means not known yet, and is pinned by the first
# authorised build rather than guessed.
SOURCES: dict[str, ModelSource] = {
    "yolo11m.pt": ModelSource(
        name="yolo11m.pt",
        role="detector",
        url="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11m.pt",
        publisher="Ultralytics (GitHub release ultralytics/assets v8.3.0)",
        bytes=40_684_120,  # release asset size, read from the GitHub API on 2026-11-16
        sha256=None,  # the release publishes no digest; record it at the first build
        note="Pretrained COCO detector. Licence: AGPL-3.0 or Ultralytics Enterprise.",
    ),
    "rtmw-x_simcc-cocktail14_pt-ucoco_270e-384x288-f840f204_20231122.pth": ModelSource(
        name="rtmw-x_simcc-cocktail14_pt-ucoco_270e-384x288-f840f204_20231122.pth",
        role="pose checkpoint (input to the ONNX export, not loaded by the worker)",
        url="https://download.openmmlab.com/mmpose/v1/projects/rtmw/"
        "rtmw-x_simcc-cocktail14_pt-ucoco_270e-384x288-f840f204_20231122.pth",
        publisher="OpenMMLab MMPose (RTMW project)",
        sha256_prefix="f840f204",  # checked in Colab in Phase 1: the hash starts with it
        note="Trained on the 14-dataset 'cocktail14' mix. Checkpoint terms unresolved.",
    ),
}

# The pose model the worker loads: an ONNX export of the checkpoint above. Exports are not
# bit-for-bit reproducible, so there is no single right hash; the manifest written at build
# time pins the one that was built. Known exports, for reference:
KNOWN_POSE_EXPORTS = {
    # made in Colab on 2026-11-15 from the public checkpoint; produced the saved reference
    # pose data for the three public test clips
    "5ff227bff950d1d1ace40631df82e2d6c8f6245b274446b5d66aaa05e7c67b29": "phase 1 reference export",
}
POSE_ONNX_BYTES = 368_740_410  # both exports seen so far have exactly this size


@dataclass(frozen=True)
class OnnxContract:
    """What the estimator needs from the pose model. A different RTMW generation can have
    the same shapes and a different score scale, so shapes alone are necessary, not
    sufficient: the checksum is what identifies the file."""

    input_shape: tuple = (1, 3, 384, 288)  # N, C, H, W
    outputs: tuple = (("simcc_x", (1, NUM_KEYPOINTS, 576)), ("simcc_y", (1, NUM_KEYPOINTS, 768)))


class ModelError(Exception):
    """A model file is missing, altered, or not the model this code was written for."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(models_dir: Path) -> dict[str, dict[str, Any]] | None:
    """{file name: {"sha256", "bytes", ...}} from the models folder, or None if absent."""
    path = models_dir / MANIFEST_NAME
    if not path.exists():
        return None
    try:
        files = json.loads(path.read_text()).get("files")
    except (ValueError, AttributeError) as e:
        raise ModelError("model_manifest_invalid", "The model manifest cannot be read.") from e
    if not isinstance(files, dict):
        raise ModelError("model_manifest_invalid", "The model manifest cannot be read.")
    return files


def write_manifest(models_dir: Path, files: dict[str, dict[str, Any]]) -> Path:
    path = models_dir / MANIFEST_NAME
    path.write_text(json.dumps({"files": files}, indent=2, sort_keys=True) + "\n")
    return path


def verify_file(path: Path, manifest: dict | None, strict: bool) -> dict[str, Any]:
    """Check one model file and return what it is (name, bytes, sha256, verified).

    With a manifest entry the size and hash must match. Without one: refused in strict
    mode; elsewhere the hash is computed and recorded, marked as not verified."""
    if not path.is_file():
        raise ModelError("model_missing", f"Model file {path.name} is not installed.")
    size = path.stat().st_size
    expected = (manifest or {}).get(path.name)
    if expected is None:
        if strict:
            raise ModelError(
                "model_not_in_manifest",
                f"{path.name} is not listed in the model manifest; refusing to load it.",
            )
        return {"name": path.name, "bytes": size, "sha256": sha256_of(path), "verified": False}
    if expected.get("bytes") not in (None, size):
        raise ModelError(
            "model_checksum_mismatch", f"{path.name} does not have the size the manifest records."
        )
    actual = sha256_of(path)
    if actual != expected.get("sha256"):
        raise ModelError(
            "model_checksum_mismatch", f"{path.name} does not match the checksum in the manifest."
        )
    return {"name": path.name, "bytes": size, "sha256": actual, "verified": True}


def _dims(shape) -> tuple:
    """ONNX dimensions with symbolic ones (a named batch size) as None."""
    return tuple(d if isinstance(d, int) else None for d in shape)


def _fits(actual: tuple, wanted: tuple) -> bool:
    return len(actual) == len(wanted) and all(
        a is None or a == w for a, w in zip(actual, wanted, strict=True)
    )


def check_onnx_io(session: Any, contract: OnnxContract | None = None) -> dict[str, Any]:
    """Check an ONNX Runtime session against what the estimator expects: one image input of
    384x288 and the two SimCC outputs for 133 points."""
    contract = contract or OnnxContract()
    inputs, outputs = session.get_inputs(), session.get_outputs()
    if len(inputs) != 1 or not _fits(_dims(inputs[0].shape), contract.input_shape):
        got = [(_i.name, _dims(_i.shape)) for _i in inputs]
        raise ModelError(
            "model_incompatible",
            f"The pose model's input is {got}; expected one input of {contract.input_shape}.",
        )
    by_name = {o.name: _dims(o.shape) for o in outputs}
    for name, shape in contract.outputs:
        if name not in by_name or not _fits(by_name[name], shape):
            raise ModelError(
                "model_incompatible",
                f"The pose model's output {name!r} is {by_name.get(name)}; expected {shape}.",
            )
    return {"input": inputs[0].name, "outputs": by_name}


def check_provider(session: Any, device: str) -> list[str]:
    """ONNX Runtime silently falls back to the CPU when the GPU provider cannot start. A
    worker that was asked for a GPU and is quietly running on the CPU would be about a
    hundred times slower and bill for it, so that is an error here, not a warning."""
    providers = list(session.get_providers())
    if device.startswith("cuda") and "CUDAExecutionProvider" not in providers:
        raise ModelError(
            "gpu_unavailable",
            "A GPU was requested but the pose model is not running on it "
            f"(active: {', '.join(providers) or 'none'}).",
        )
    return providers


def is_strict() -> bool:
    """Strict: every model file must be in the manifest and nothing may be downloaded at
    run time. Always on outside local development."""
    if os.environ.get("AQUATRACK_MODELS_STRICT", "").strip() in ("1", "true", "yes"):
        return True
    return os.environ.get("AQUATRACK_ENV", "emulator").strip().lower() in ("staging", "production")


@dataclass
class Preflight:
    ok: bool = False
    device: str = "cpu"
    strict: bool = False
    files: list[dict[str, Any]] = field(default_factory=list)
    versions: dict[str, str] = field(default_factory=dict)
    providers: list[str] = field(default_factory=list)
    onnx: dict[str, Any] = field(default_factory=dict)
    smoke_test: str = "not run"
    error_code: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_preflight(
    models_dir: Path,
    detector_weights: str,
    pose_weights: str,
    device: str,
    strict: bool,
    load: Callable[[Path, Path, str], Any],
    versions: Callable[[], dict[str, str]] | None = None,
) -> Preflight:
    """Everything that must be true before the worker takes a job. `load` builds the real
    estimator (detector + pose model) and is only called once the files have passed; it
    returns an object with `pose_session` and `smoke()`. Never raises: the report says what
    failed, in words that are safe to log (no paths beyond file names, no secrets)."""
    report = Preflight(device=device, strict=strict)
    try:
        manifest = load_manifest(models_dir)
        if manifest is None and strict:
            raise ModelError(
                "model_manifest_missing",
                "No model manifest is installed; refusing to load unverified model files.",
            )
        for name in (detector_weights, pose_weights):
            report.files.append(verify_file(models_dir / name, manifest, strict))
        if versions:
            report.versions = versions()
        loaded = load(models_dir / detector_weights, models_dir / pose_weights, device)
        report.onnx = check_onnx_io(loaded.pose_session)
        report.providers = check_provider(loaded.pose_session, device)
        report.smoke_test = loaded.smoke()
        report.ok = True
    except ModelError as e:
        report.error_code, report.error = e.code, e.message
    except ImportError:
        report.error_code = "pose_dependencies_missing"
        report.error = "The pose extra is not installed (uv sync --extra pose)."
    except Exception as e:  # a CUDA or model-loading failure: report its kind, not its text
        report.error_code = "model_load_failed"
        report.error = f"The models could not be loaded ({type(e).__name__})."
    return report
