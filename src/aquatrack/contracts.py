"""Versioned data contracts shared by pose inference, processing, the API and the web app.

Flow: RawPose (model output, never edited) -> ProcessedPose (cleaned, every point labelled
observed / interpolated / rejected / missing) -> AnalysisResult (what the app stores and
shows). Raw and processed data are separate objects and separate files.

Array-carrying contracts (RawPose, ProcessedPose) are saved as .npz with a JSON `meta`
entry; everything else is plain JSON. Bump `SCHEMA_VERSION` on any breaking change.
"""

import json
import os
from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0"
NUM_KEYPOINTS = 133
# RawPose files written by the student's CLI before this schema existed.
LEGACY_SCHEMA_VERSION = "0"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# ---------- model configuration ----------


class ModelConfig(BaseModel):
    """Which models run and how. Recorded with every raw pose and analysis result.

    The defaults are the engineering baseline chosen from the detector / RTMW comparison
    (underwater side-view footage). They are a practical baseline, not proof of accuracy
    on every kind of video, and every field can be overridden.
    """

    model_config = ConfigDict(frozen=True, protected_namespaces=())

    detector_weights: str = "yolo11m.pt"
    detector_imgsz: int = Field(640, ge=32)
    detector_confidence: float = Field(0.15, ge=0, le=1)
    target_selection: Literal["tracking", "largest"] = "tracking"
    max_box_carry_s: float = Field(0.5, ge=0)
    pose_model: str = "rtmw-x"
    pose_weights: str = "rtmw_x_stock.onnx"
    pose_input_width: int = 288
    pose_input_height: int = 384
    frame_step: int = Field(1, ge=1)

    @classmethod
    def from_env(cls) -> "ModelConfig":
        """Defaults, overridden by AQUATRACK_* environment variables when set."""
        names = {
            "detector_weights": "AQUATRACK_DETECTOR_WEIGHTS",
            "detector_imgsz": "AQUATRACK_DETECTOR_IMGSZ",
            "detector_confidence": "AQUATRACK_DETECTOR_CONFIDENCE",
            "target_selection": "AQUATRACK_TARGET_SELECTION",
            "pose_weights": "AQUATRACK_POSE_WEIGHTS",
            "frame_step": "AQUATRACK_FRAME_STEP",
        }
        values = {field: os.environ[env] for field, env in names.items() if os.environ.get(env)}
        return cls(**values)


class ModelInfo(BaseModel):
    """One model as it actually ran: file name and, when known, a content hash."""

    name: str
    version: str = ""
    sha256: str | None = None


class VideoIdentity(BaseModel):
    """What ties pose data to one exact video file."""

    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frame_count: int = Field(ge=0)  # frames actually decoded, not the container's estimate
    fps: float = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)

    @property
    def duration_s(self) -> float:
        return self.frame_count / self.fps


class Provenance(BaseModel):
    """Where a pose file came from."""

    source: Literal["precomputed", "local", "remote", "legacy"]
    produced_by: str = ""  # e.g. "colab", "aquatrack cli"
    created_at: str = Field(default_factory=_now)
    notes: str = ""


# ---------- raw pose ----------


class BoxSource(IntEnum):
    NONE = 0  # no box this frame
    DETECTED = 1  # from the detector
    CARRIED = 2  # detector missed; last box carried forward


class Selection(IntEnum):
    """How the target swimmer's box was chosen among the detected people."""

    NONE = 0
    FIRST = 1  # first box of a track: largest area x confidence
    OVERLAP = 2  # overlapped the previous box
    NEAREST = 3  # no overlap; nearest to the previous box
    LARGEST = 4  # largest box (the pre-tracking rule)
    CARRIED = 5
    UNKNOWN = 6  # legacy files


class RawPoseMeta(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    schema_version: str = SCHEMA_VERSION
    video: VideoIdentity | None = None  # None only for legacy files
    video_id: str | None = None
    fps: float = Field(gt=0)  # rate of the analysed frames (video fps / frame_step)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    config: ModelConfig | None = None
    detector: ModelInfo | None = None
    pose: ModelInfo
    provenance: Provenance


class RawPose(BaseModel):
    """Unedited model output for one video.

    keypoints: (frames, 133, 3) x and y normalized to the frame, and the model's raw score.
    Frames with no swimmer box are NaN. boxes: (frames, 4) x1, y1, x2, y2 in pixels, NaN
    when there is none (or the file is legacy and never recorded them).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    meta: RawPoseMeta
    frame_indices: np.ndarray  # (frames,) source video frame numbers
    timestamps_s: np.ndarray  # (frames,)
    keypoints: np.ndarray
    boxes: np.ndarray
    box_confidence: np.ndarray  # (frames,) detector score, NaN when carried or unknown
    box_source: np.ndarray  # (frames,) BoxSource
    selection: np.ndarray  # (frames,) Selection
    candidates: np.ndarray  # (frames,) person boxes the detector returned; -1 unknown

    @model_validator(mode="after")
    def _check_shapes(self) -> "RawPose":
        n = len(self.frame_indices)
        if self.keypoints.shape != (n, NUM_KEYPOINTS, 3):
            raise ValueError(f"keypoints must be ({n}, {NUM_KEYPOINTS}, 3)")
        if self.boxes.shape != (n, 4):
            raise ValueError(f"boxes must be ({n}, 4)")
        for name in ("timestamps_s", "box_confidence", "box_source", "selection", "candidates"):
            if getattr(self, name).shape != (n,):
                raise ValueError(f"{name} must have one value per frame ({n})")
        if n > 1 and not (np.diff(self.frame_indices) > 0).all():
            raise ValueError("frame_indices must increase")
        return self

    def __len__(self) -> int:
        return len(self.frame_indices)

    @property
    def has_boxes(self) -> bool:
        return bool(np.isfinite(self.boxes).any())

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        np.savez_compressed(
            path,
            meta=self.meta.model_dump_json(),
            frame_indices=self.frame_indices.astype(np.int64),
            timestamps_s=self.timestamps_s.astype(np.float64),
            keypoints=self.keypoints.astype(np.float32),
            boxes=self.boxes.astype(np.float32),
            box_confidence=self.box_confidence.astype(np.float32),
            box_source=self.box_source.astype(np.uint8),
            selection=self.selection.astype(np.uint8),
            candidates=self.candidates.astype(np.int16),
        )
        return path

    @classmethod
    def load(cls, path: str | Path) -> "RawPose":
        """Read a RawPose .npz, or a legacy `.wholebody.npz` from the student's CLI.

        Raises ValueError for anything else: wrong arrays, unknown schema, corrupt file.
        """
        try:
            with np.load(path, allow_pickle=False) as data:
                files = set(data.files)
                if "meta" in files:
                    meta = RawPoseMeta.model_validate_json(str(data["meta"]))
                    # "0" is a legacy file that was re-saved in this format.
                    known = (SCHEMA_VERSION.split(".")[0], LEGACY_SCHEMA_VERSION)
                    if meta.schema_version.split(".")[0] not in known:
                        raise ValueError(
                            f"unsupported RawPose schema {meta.schema_version!r} "
                            f"(this build reads {SCHEMA_VERSION})"
                        )
                    return cls(
                        meta=meta,
                        frame_indices=data["frame_indices"],
                        timestamps_s=data["timestamps_s"],
                        keypoints=data["keypoints"].astype(np.float64),
                        boxes=data["boxes"].astype(np.float64),
                        box_confidence=data["box_confidence"].astype(np.float64),
                        box_source=data["box_source"],
                        selection=data["selection"],
                        candidates=data["candidates"],
                    )
                if {"keypoints", "fps", "frame_indices", "width", "height"} <= files:
                    return cls._from_legacy(data)
        except ValueError:
            raise
        except Exception as e:  # zipfile.BadZipFile, KeyError, OSError, pydantic errors
            raise ValueError(f"not a readable pose file: {e}") from e
        raise ValueError("not a pose file: expected RawPose or legacy wholebody arrays")

    @classmethod
    def _from_legacy(cls, data) -> "RawPose":
        keypoints = data["keypoints"].astype(np.float64)
        n = len(keypoints)
        fps = float(data["fps"])
        frame_indices = data["frame_indices"]
        step = int(frame_indices[1] - frame_indices[0]) if n > 1 else 1
        return cls(
            meta=RawPoseMeta(
                schema_version=LEGACY_SCHEMA_VERSION,
                fps=fps,
                width=int(data["width"]),
                height=int(data["height"]),
                pose=ModelInfo(name=str(data["model"]) if "model" in data.files else "unknown"),
                provenance=Provenance(
                    source="legacy",
                    produced_by="aquatrack cli (.wholebody.npz)",
                    notes="No boxes, detector or video hash were recorded.",
                ),
            ),
            frame_indices=frame_indices,
            timestamps_s=frame_indices / (fps * step),
            keypoints=keypoints,
            boxes=np.full((n, 4), np.nan),
            box_confidence=np.full(n, np.nan),
            box_source=np.zeros(n, np.uint8),
            selection=np.full(n, int(Selection.UNKNOWN), np.uint8),
            candidates=np.full(n, -1, np.int16),
        )


# ---------- processed pose ----------


class JointState(IntEnum):
    MISSING = 0  # the model gave nothing here (no swimmer box, or never filled)
    OBSERVED = 1  # the model's point, kept (possibly smoothed or left/right swapped back)
    INTERPOLATED = 2  # estimated across a short gap; low confidence
    REJECTED = 3  # the model gave a point but processing threw it out


class RejectReason(IntEnum):
    """Bit flags. The first six match `cleanup.Fix`; the rest are added by processing."""

    LOW_SCORE = 1
    BAD_FRAME = 2
    IMPOSSIBLE = 4
    SPIKE = 8
    SWAPPED = 16  # not a rejection: left/right swapped back, kept for provenance
    FILLED = 32  # not a rejection: see JointState.INTERPOLATED
    OTHER_SWIMMER = 64  # frame belongs to a different person than the target swimmer


class Segment(BaseModel):
    """A run of frames that follows one person. Indices are into the analysed frames."""

    start: int
    end: int  # inclusive
    accepted: bool  # False: judged to be someone other than the target swimmer


class ProcessedPoseMeta(BaseModel):
    schema_version: str = SCHEMA_VERSION
    video_sha256: str | None = None
    raw_schema_version: str
    fps: float
    width: int
    height: int
    flipped: bool  # x mirrored so the swimmer's head points right
    segments: list[Segment] = []
    processing: dict[str, float | str] = {}  # thresholds used (see docs/POSE_PROCESSING.md)


class ProcessedPose(BaseModel):
    """Cleaned pose with per-point provenance. Coordinates are pixels in the oriented frame
    (mirrored when `meta.flipped`), NaN where state is MISSING or REJECTED."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    meta: ProcessedPoseMeta
    frame_indices: np.ndarray
    timestamps_s: np.ndarray
    xy: np.ndarray  # (frames, 133, 2)
    confidence: np.ndarray  # (frames, 133), 0-1
    state: np.ndarray  # (frames, 133) JointState
    reasons: np.ndarray  # (frames, 133) RejectReason bit flags
    trunk: np.ndarray  # (frames,) shoulder-to-hip length in pixels

    @model_validator(mode="after")
    def _check(self) -> "ProcessedPose":
        n = len(self.frame_indices)
        if self.xy.shape != (n, NUM_KEYPOINTS, 2):
            raise ValueError("xy has the wrong shape")
        for name in ("confidence", "state", "reasons"):
            if getattr(self, name).shape != (n, NUM_KEYPOINTS):
                raise ValueError(f"{name} has the wrong shape")
        usable = np.isin(self.state, (JointState.OBSERVED, JointState.INTERPOLATED))
        if np.isnan(self.xy[..., 0])[usable].any() or np.isfinite(self.xy[..., 0])[~usable].any():
            raise ValueError("coordinates and joint states disagree")
        return self

    def __len__(self) -> int:
        return len(self.frame_indices)

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        np.savez_compressed(
            path,
            meta=self.meta.model_dump_json(),
            frame_indices=self.frame_indices.astype(np.int64),
            timestamps_s=self.timestamps_s.astype(np.float64),
            xy=self.xy.astype(np.float32),
            confidence=self.confidence.astype(np.float32),
            state=self.state.astype(np.uint8),
            reasons=self.reasons.astype(np.uint16),
            trunk=self.trunk.astype(np.float32),
        )
        return path

    @classmethod
    def load(cls, path: str | Path) -> "ProcessedPose":
        with np.load(path, allow_pickle=False) as data:
            return cls(
                meta=ProcessedPoseMeta.model_validate_json(str(data["meta"])),
                frame_indices=data["frame_indices"],
                timestamps_s=data["timestamps_s"],
                xy=data["xy"].astype(np.float64),
                confidence=data["confidence"].astype(np.float64),
                state=data["state"],
                reasons=data["reasons"],
                trunk=data["trunk"].astype(np.float64),
            )


# ---------- quality ----------


class QualityGrade(StrEnum):
    GOOD = "good"
    LIMITED = "limited"
    INSUFFICIENT = "insufficient"


class Unavailable(BaseModel):
    key: str
    label: str
    reason: str


class TrackingQuality(BaseModel):
    """How reliably one swimmer's box was followed."""

    recorded: bool  # False for legacy pose files without boxes
    detected_pct: float | None = None
    carried_pct: float | None = None
    no_box_pct: float | None = None
    multiple_people_pct: float | None = None  # frames where the detector saw 2+ people
    identity_breaks: int = 0  # places where the box jumped to a different person
    other_swimmer_pct: float = 0.0  # frames rejected as not the target swimmer


class QualityReport(BaseModel):
    """How much of the clip could be trusted. Percentages are 0-100.

    Joint percentages are over the 12 limb joints (shoulders, elbows, wrists, hips, knees,
    ankles) of the analysed frames.
    """

    total_frames: int  # frames in the video
    analyzed_frames: int  # frames the pose model was run on
    frames_with_swimmer: int
    valid_pose_frames: int
    valid_pose_pct: float
    observed_pct: float
    interpolated_pct: float
    rejected_pct: float
    missing_pct: float
    per_joint_coverage: dict[str, float]  # usable (observed or interpolated) % per body joint
    body_part_coverage: dict[str, float]  # head, trunk, arms, legs, hands, feet
    longest_missing_s: float  # longest run without a valid pose
    tracking: TrackingQuality
    reliable_stroke_cycles: int
    grade: QualityGrade
    grade_reasons: list[str]  # which criteria decided the grade
    filming_limitations: list[str]  # known limits of this view / stroke; never affect the grade
    unavailable: list[Unavailable] = []


# ---------- analysis result ----------


class Measurement(BaseModel):
    key: str
    label: str
    value: float
    unit: str
    confidence: float | None = None  # 0-1
    basis: str = ""  # what it was computed from, e.g. "7 trusted cycles of the right arm"


class StrokeCycleOut(BaseModel):
    arm: Literal["left", "right"]
    start_s: float
    end_s: float
    duration_s: float
    trusted: bool
    reason: str = ""
    section: str = ""


class SectionOut(BaseModel):
    name: str
    start_s: float
    end_s: float


class StrokeSummary(BaseModel):
    measurable: bool
    reason: str = ""  # why not, when measurable is False
    # Trusted arm cycles seen in the clip (one cycle = one full turn of one arm).
    cycle_count: dict[str, int] = {}
    # Left + right arm cycles, only when every cycle in the clip was followed; else None.
    stroke_count: int | None = None
    cycles_per_min: dict[str, float | None] = {}
    cycles: list[StrokeCycleOut] = []


class Timing(BaseModel):
    clip_duration_s: float
    swim_start_s: float | None = None  # main stretch where the swimmer is tracked
    swim_end_s: float | None = None
    sections: list[SectionOut] = []
    median_cycle_s: float | None = None


class SessionInfo(BaseModel):
    """What the swimmer said about the clip (from the upload form)."""

    stroke: str = ""
    camera: str = ""
    distance: str = ""
    pool_length: str = ""


class ArtifactRef(BaseModel):
    kind: Literal["raw_pose", "processed_pose"]
    storage_path: str
    bytes: int | None = None


class AnalysisResult(BaseModel):
    """Analysis v1: basic stroke timing plus an honest account of data quality.

    No posture scores, issues or corrections: those wait for validated biomechanics metrics.
    """

    schema_version: str = SCHEMA_VERSION
    engine_version: str
    video_id: str
    video: VideoIdentity
    session: SessionInfo
    config: ModelConfig | None
    detector: ModelInfo | None
    pose: ModelInfo
    pose_source: str  # provenance.source of the raw pose
    stroke: StrokeSummary
    timing: Timing
    quality: QualityReport
    measurements: list[Measurement] = []
    unavailable: list[Unavailable] = []
    artifacts: list[ArtifactRef] = []
    created_at: str = Field(default_factory=_now)

    def to_firestore(self) -> dict:
        return json.loads(self.model_dump_json())


# ---------- jobs ----------


class AnalysisJobStatus(StrEnum):
    UPLOADED = "uploaded"  # stored, analysis never requested
    QUEUED = "queued"
    ANALYZING = "analyzing"
    READY = "ready"
    FAILED = "failed"


class JobError(BaseModel):
    code: str  # stable, machine-readable
    message: str  # safe to show to the swimmer: no file paths or internals
    retryable: bool


class AnalysisJob(BaseModel):
    """Job state kept on the video's Firestore document under `job`."""

    status: AnalysisJobStatus
    attempts: int = 0
    queued_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    pose_source: str | None = None
    error: JobError | None = None
    analysis_id: str | None = None
