"""Where raw pose data comes from. Every source returns the same validated `RawPose`.

  precomputed  pose files made elsewhere (Google Colab during development), matched to the
               uploaded video by its SHA-256. A development and testing strategy only: a
               video nobody ran the models on has no pose data and the job fails, clearly.
  local        the RTMW pipeline in this process. Optional: needs the `pose` extra and the
               model weights, which ordinary app development does not install.
  remote       a dedicated inference worker (GPU service). Interface only for now; this is
               the path that will let any newly uploaded video be analysed in production.

Nothing here ever substitutes example or mock data for missing pose data.
"""

import os
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from aquatrack.contracts import ModelConfig, RawPose, VideoIdentity

# Two decoders can disagree by a frame or two at the end of some files.
FRAME_COUNT_TOLERANCE = 2
FPS_TOLERANCE = 0.01
PRECOMPUTED_SUFFIX = ".rawpose.npz"


class PoseSourceError(Exception):
    """Pose data could not be produced. `message` is safe to show to the swimmer."""

    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class PoseSource(Protocol):
    name: str

    def get_raw_pose(self, video_path: Path, video: VideoIdentity, video_id: str) -> RawPose:
        """Raw pose for exactly this video file, or raise PoseSourceError."""
        ...


def validate_raw_pose(raw: RawPose, video: VideoIdentity) -> None:
    """Check that `raw` really belongs to `video` and is complete enough to analyse.

    Shared by every source, so data from Colab, a local model or a worker is held to the
    same standard before it reaches processing.
    """
    recorded = raw.meta.video
    if recorded is None:
        raise PoseSourceError(
            "pose_data_unverifiable",
            "The pose data for this video does not say which video it was made from.",
        )
    if recorded.sha256 != video.sha256:
        raise PoseSourceError(
            "pose_video_mismatch", "The pose data was made from a different video file."
        )
    if (recorded.width, recorded.height) != (video.width, video.height):
        raise PoseSourceError(
            "pose_video_mismatch", "The pose data was made at a different video size."
        )
    if abs(recorded.fps - video.fps) > FPS_TOLERANCE:
        raise PoseSourceError(
            "pose_video_mismatch", "The pose data was made at a different frame rate."
        )
    if abs(recorded.frame_count - video.frame_count) > FRAME_COUNT_TOLERANCE:
        raise PoseSourceError(
            "pose_video_mismatch",
            "The pose data covers a different number of frames than this video.",
        )
    if len(raw) == 0:
        raise PoseSourceError("pose_data_invalid", "The pose data for this video is empty.")
    if int(raw.frame_indices[-1]) >= video.frame_count + FRAME_COUNT_TOLERANCE:
        raise PoseSourceError(
            "pose_video_mismatch", "The pose data refers to frames this video does not have."
        )
    if raw.meta.config is None or raw.meta.detector is None:
        raise PoseSourceError(
            "pose_data_invalid", "The pose data does not record which models produced it."
        )


MISSING_POSE = (
    "No pose data has been prepared for this video yet. During development, pose "
    "data is produced separately for each test video."
)
# The restricted demonstration: only the approved test video has pose data, the models do
# not run there, and trying again cannot change that.
DEMO_UNSUPPORTED = (
    "This video can't be analysed in the demonstration environment. The demonstration "
    "analyses only the approved test video, using pose data that was extracted from that "
    "exact file in advance. The pose models do not run here, and data from another video "
    "is never used in its place."
)


class PrecomputedPoseSource:
    """Pose files named `<video sha256>.rawpose.npz` in one folder. `fetch(sha256, path)`
    may bring a missing file into the folder (the demonstration keeps its one file in the
    project's own bucket); it returns whether it did. A file is only ever looked up by the
    SHA-256 of the uploaded video, and validate_raw_pose still checks it against the video."""

    name = "precomputed"

    def __init__(
        self,
        directory: str | Path,
        fetch: Callable[[str, Path], bool] | None = None,
        missing_message: str = MISSING_POSE,
        missing_retryable: bool = True,
    ):
        self.directory = Path(directory)
        self.fetch = fetch
        self.missing_message = missing_message
        self.missing_retryable = missing_retryable

    def path_for(self, sha256: str) -> Path:
        return self.directory / f"{sha256}{PRECOMPUTED_SUFFIX}"

    def get_raw_pose(self, video_path: Path, video: VideoIdentity, video_id: str) -> RawPose:
        path = self.path_for(video.sha256)
        if not path.is_file() and self.fetch is not None:
            try:
                self.fetch(video.sha256, path)
            except Exception as e:
                raise PoseSourceError(
                    "pose_data_unavailable",
                    "The prepared pose data could not be loaded just now.",
                    retryable=True,
                ) from e
        if not path.is_file():
            raise PoseSourceError(
                "pose_data_missing", self.missing_message, retryable=self.missing_retryable
            )
        try:
            raw = RawPose.load(path)
        except ValueError as e:
            raise PoseSourceError(
                "pose_data_invalid", "The pose data for this video could not be read."
            ) from e
        validate_raw_pose(raw, video)
        raw.meta.video_id = video_id
        return raw


def pose_device() -> str:
    """AQUATRACK_POSE_DEVICE = cpu (default) | cuda | mps."""
    return os.environ.get("AQUATRACK_POSE_DEVICE", "cpu").strip().lower() or "cpu"


class _Loaded:
    """The estimator as loaded, with what the preflight needs to look at."""

    def __init__(self, estimator):
        self.estimator = estimator
        self.pose_session = estimator._pose_model.session

    def smoke(self) -> str:
        """One blank frame through both models. It proves they run on this machine; it
        says nothing about accuracy."""
        import numpy as np

        points = self.estimator.estimate_frame(np.zeros((480, 640, 3), dtype=np.uint8))
        return f"ran on a blank frame ({points.shape[0]} points returned)"


class LocalModelPoseSource:
    """Runs the detector and RTMW in this process: the source a real inference worker uses.

    Before the first video the model files are checked against the manifest that was
    written when the image was built, the pose model's inputs and outputs are checked, and
    a GPU that was asked for must really be in use (`preflight`). In strict mode (always
    outside local development) a file that is not in the manifest is refused and nothing is
    ever downloaded at run time. Heavy imports happen on first use."""

    name = "local"
    supports_progress = True

    def __init__(self, config: ModelConfig, device: str | None = None):
        self.config = config
        self.device = device or pose_device()
        self._estimator = None
        self._files: dict[str, dict] = {}
        self._versions: dict[str, str] = {}

    def _build(self, detector_path: Path, pose_path: Path, device: str) -> _Loaded:
        from aquatrack.analysis.pose.rtmw_backend import RtmwEstimator, YoloPersonDetector

        detector = YoloPersonDetector.from_config(
            self.config.model_copy(update={"detector_weights": str(detector_path)}),
            device=None if device == "cpu" else device,
            offline=True,
        )
        return _Loaded(
            RtmwEstimator(
                pose_path,
                detector=detector,
                device=device,
                target_selection=self.config.target_selection,
            )
        )

    @staticmethod
    def _library_versions() -> dict[str, str]:
        from importlib.metadata import PackageNotFoundError, version

        found = {}
        for package in ("ultralytics", "rtmlib", "onnxruntime", "onnxruntime-gpu", "torch"):
            try:
                found[package] = version(package)
            except PackageNotFoundError:
                continue
        return found

    def preflight(self):
        """Check the models and load them. Returns the report; `ok` says whether this
        worker may take jobs."""
        from aquatrack.analysis.pose import manifest
        from aquatrack.analysis.pose.rtmw_backend import MODELS_DIR

        loaded: list[_Loaded] = []

        def load(detector_path, pose_path, device):
            loaded.append(self._build(detector_path, pose_path, device))
            return loaded[0]

        report = manifest.run_preflight(
            MODELS_DIR,
            Path(self.config.detector_weights).name,
            Path(self.config.pose_weights).name,
            self.device,
            manifest.is_strict(),
            load,
            self._library_versions,
        )
        if report.ok:
            self._estimator = loaded[0].estimator
            self._files = {f["name"]: f for f in report.files}
            self._versions = report.versions
        return report

    def _load(self):
        if self._estimator is None:
            report = self.preflight()
            if not report.ok:
                # Not retryable: the same image would fail the same way on every attempt.
                raise PoseSourceError(
                    report.error_code or "local_model_unavailable",
                    "The analysis service is not set up correctly. Nothing is wrong with "
                    "your video.",
                )
        return self._estimator

    def get_raw_pose(
        self, video_path: Path, video: VideoIdentity, video_id: str, progress=None
    ) -> RawPose:
        estimator = self._load()
        raw = estimator.estimate_raw(
            video_path,
            config=self.config,
            video_id=video_id,
            source="local",
            produced_by="worker",
            on_frame=progress,
        )
        # Record exactly which files and library versions produced this pose.
        detector = self._files.get(Path(self.config.detector_weights).name, {})
        raw.meta.detector.sha256 = detector.get("sha256")
        raw.meta.detector.version = f"ultralytics {self._versions.get('ultralytics', '?')}"
        runtime = self._versions.get("onnxruntime-gpu") or self._versions.get("onnxruntime", "?")
        raw.meta.pose.version = f"onnxruntime {runtime} on {self.device}"
        validate_raw_pose(raw, video)
        return raw


class RemoteWorkerPoseSource:
    """A separate inference service. Not built yet.

    Planned contract: the API hands the worker a short-lived link to the video plus the
    `ModelConfig`; the worker returns a RawPose file (same schema, provenance "remote"),
    which is then checked with `validate_raw_pose` like any other source.
    """

    name = "remote"

    def __init__(self, url: str | None = None):
        self.url = url

    def get_raw_pose(self, video_path: Path, video: VideoIdentity, video_id: str) -> RawPose:
        raise PoseSourceError(
            "remote_worker_unavailable", "The analysis service is not available yet."
        )


def pose_source_from_env(config: ModelConfig | None = None) -> PoseSource:
    """AQUATRACK_POSE_SOURCE = precomputed (default) | local | remote."""
    kind = os.environ.get("AQUATRACK_POSE_SOURCE", "precomputed").lower()
    if kind == "precomputed":
        return PrecomputedPoseSource(
            os.environ.get("AQUATRACK_PRECOMPUTED_POSE_DIR", "data/precomputed_pose")
        )
    if kind == "local":
        return LocalModelPoseSource(config or ModelConfig.from_env())
    if kind == "remote":
        return RemoteWorkerPoseSource(os.environ.get("AQUATRACK_WORKER_URL"))
    raise ValueError(f"Unknown AQUATRACK_POSE_SOURCE {kind!r}")
