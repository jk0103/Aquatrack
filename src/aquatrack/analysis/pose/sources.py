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


class PrecomputedPoseSource:
    """Pose files named `<video sha256>.rawpose.npz` in one folder."""

    name = "precomputed"

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)

    def path_for(self, sha256: str) -> Path:
        return self.directory / f"{sha256}{PRECOMPUTED_SUFFIX}"

    def get_raw_pose(self, video_path: Path, video: VideoIdentity, video_id: str) -> RawPose:
        path = self.path_for(video.sha256)
        if not path.is_file():
            raise PoseSourceError(
                "pose_data_missing",
                "No pose data has been prepared for this video yet. During development, pose "
                "data is produced separately for each test video.",
                retryable=True,
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


class LocalModelPoseSource:
    """Runs the detector and RTMW in this process. Heavy imports happen on first use."""

    name = "local"

    def __init__(self, config: ModelConfig, device: str = "cpu"):
        self.config = config
        self.device = device
        self._estimator = None

    def _load(self):
        if self._estimator is None:
            try:
                from aquatrack.analysis.pose.rtmw_backend import (
                    MODELS_DIR,
                    RtmwEstimator,
                    YoloPersonDetector,
                )

                detector = YoloPersonDetector.from_config(self.config)
                self._estimator = RtmwEstimator(
                    MODELS_DIR / self.config.pose_weights,
                    detector=detector,
                    device=self.device,
                    target_selection=self.config.target_selection,
                )
            except (ImportError, FileNotFoundError) as e:
                raise PoseSourceError(
                    "local_model_unavailable",
                    "Pose models are not installed on this server.",
                ) from e
        return self._estimator

    def get_raw_pose(self, video_path: Path, video: VideoIdentity, video_id: str) -> RawPose:
        raw = self._load().estimate_raw(
            video_path, config=self.config, video_id=video_id, source="local"
        )
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
