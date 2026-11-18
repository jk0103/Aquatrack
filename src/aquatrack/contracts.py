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

SCHEMA_VERSION = "1.0"  # pose files (RawPose, ProcessedPose)
# Analysis results. 1.1 adds `metrics` and `coverage` and more detail on stroke cycles; it
# only adds fields, so 1.0 results stay readable and are never rewritten. 1.2 adds the five
# exclusive arm classes (`ArmObservation.*_pct`), `coverage.view` and `Metric.excluded_cycles`.
ANALYSIS_SCHEMA_VERSION = "1.2"
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
    # 1.1: why an untrusted cycle is unclear: "merged" (looks like two cycles, a pull was not
    # seen), "fragment" (too short to be a cycle), "hidden" (arm not seen well enough).
    kind: str = ""


class PartialCycleOut(BaseModel):
    """Arm movement at the edge of the clip that is not a whole cycle. Never counted."""

    arm: Literal["left", "right"]
    start_s: float
    end_s: float


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
    # 1.1
    partial: list[PartialCycleOut] = []
    counted_arm: str | None = None  # the arm the count and timing come from
    # Whole cycles of `counted_arm` between its first and last mid-pull, only when none of
    # them is unclear; else None. One cycle is two arm strokes (one per arm).
    counted_cycles: int | None = None


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


class MetricStatus(StrEnum):
    RELIABLE = "reliable"  # met every criterion set for this metric
    LIMITED = "limited"  # measured, but on thin or indirect evidence: read with the reason
    UNAVAILABLE = "unavailable"  # not shown as a number


class MetricKind(StrEnum):
    TEMPORAL = "temporal"  # timing and rhythm
    GEOMETRIC = "geometric"  # positions and angles in the picture, in body units
    PROXY = "proxy"  # a 2D stand-in for something that is really three-dimensional


class MetricSample(BaseModel):
    """One value behind a metric, usually one stroke cycle, with where to look in the video."""

    t_s: float  # a moment that shows it
    value: float
    start_s: float | None = None
    end_s: float | None = None
    label: str = ""


class Metric(BaseModel):
    """One biomechanics measurement with its own evidence and reliability.

    Definitions, criteria and limits per key: docs/BIOMECHANICS_METRICS.md.
    """

    key: str
    label: str
    group: Literal["timing", "body", "arm", "consistency"]
    kind: MetricKind
    unit: str
    description: str  # what the number means, in one sentence
    status: MetricStatus
    value: float | None = None  # median over the samples; None when unavailable
    low: float | None = None  # 25th and 75th percentile over the samples
    high: float | None = None
    n_cycles: int = 0
    excluded_cycles: int = 0  # 1.2: reliable cycles left out because of the camera view
    coverage_pct: float | None = None  # frames of those cycles where the needed joints were usable
    side: str | None = None  # the arm it was read from, for arm metrics
    samples: list[MetricSample] = []
    basis: str = ""
    reason: str = ""  # why it is limited or unavailable
    limitations: list[str] = []


class CameraSide(BaseModel):
    """Which arm faces the camera in a side view, and what that rests on."""

    arm: Literal["left", "right"] | None = None
    evidence: list[str] = []
    reason: str = ""  # why it could not be established


class ArmObservation(BaseModel):
    """What is known about one arm's elbow and wrist, as shares of the frames in the main
    stretch of swimming.

    Since 1.2 every frame is in exactly one of five classes, which add up to 100:
    supported, interpolated, model_only, rejected, missing. "Supported" means the model's
    points lie inside an underwater pull that was followed and have believable segment
    lengths; it is the only class arm metrics read. It is not a person confirming the arm
    was visible. `model_only` is what the model drew without anything to back it up; a high
    model score does not move a point out of it.
    """

    arm: Literal["left", "right"]
    camera_side: bool
    pulls: int  # underwater pulls seen passing straight down
    pulls_followed_back: int  # of those, followed to the end of the push
    # 1.2: exclusive classes (None in 1.1 documents)
    supported_pct: float | None = None
    interpolated_pct: float | None = None
    model_only_pct: float | None = None
    rejected_pct: float | None = None
    missing_pct: float | None = None
    # 1.2: parts of model_only, for explanation
    model_only_in_front_pct: float | None = None  # drawn stretched ahead; not confirmed
    model_only_collapsed_pct: float | None = None  # in a pull, segment impossibly short
    # 1.1 fields. They overlapped (interpolated points inside a pull counted as unverified)
    # and "in front" read as confirmed; kept filled for older readers only.
    followed_pct: float
    in_front_pct: float = 0.0
    unverified_pct: float
    not_observed_pct: float


class ViewSuitability(BaseModel):
    """1.2: whether the camera kept a steady view of the swimmer. Not a measured angle."""

    status: Literal["steady", "changing", "unknown"] = "unknown"
    smallest_size_share: float | None = None  # apparent trunk size, smallest / largest cycle
    cycles_left_out: int = 0
    cycles_checked: int = 0
    note: str = ""


class CycleCompleteness(BaseModel):
    arm: str | None = None  # the arm cycles are counted on
    detected: int = 0
    reliable: int = 0
    ambiguous: int = 0  # merged, fragment or hidden
    partial: int = 0  # at the clip edges
    count_measurable: bool = False
    status: Literal["complete", "partial", "none"] = "none"
    note: str = ""


class AnalysisCoverage(BaseModel):
    """What the analysis could and could not stand behind, level by level. Tracking quality
    (QualityReport.grade) is only the first level: a well tracked clip can still have
    unclear stroke cycles or metrics that cannot be measured."""

    tracking_grade: QualityGrade
    camera_side: CameraSide
    arms: list[ArmObservation] = []
    cycles: CycleCompleteness
    view: ViewSuitability | None = None  # 1.2
    metrics_reliable: int = 0
    metrics_limited: int = 0
    metrics_unavailable: int = 0
    summary: str = ""


class AnalysisResult(BaseModel):
    """Analysis result: stroke timing, biomechanics metrics that each carry their own
    reliability, and an account of what could not be measured.

    No posture scores, issues or corrections: a metric here is a measurement, not a judgement.
    Schema 1.0 results (Phase 1) have no `metrics` or `coverage`.
    """

    schema_version: str = ANALYSIS_SCHEMA_VERSION
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
    measurements: list[Measurement] = []  # 1.0 summary numbers, kept for older readers
    unavailable: list[Unavailable] = []
    metrics: list[Metric] = []  # 1.1
    coverage: AnalysisCoverage | None = None  # 1.1
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
    DELETING = "deleting"  # the swimmer asked for it to be deleted; nothing else may start
    CANCELED = "canceled"  # the swimmer stopped a queued or running analysis


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


# ---------- interpretation (Phase 3) ----------
# Stored apart from analysis results, one document per interpretation run, so saved
# metrics can be read again under newer rules without new pose inference and without
# rewriting anything. Analysis results stay at ANALYSIS_SCHEMA_VERSION.

INTERPRETATION_VERSION = "1.0"


class FindingEvidence(BaseModel):
    """One measurement a finding rests on, copied from the analysis it was read from."""

    metric_key: str
    label: str
    value: float | None = None
    unit: str = ""
    low: float | None = None
    high: float | None = None
    n_cycles: int = 0
    status: str = ""  # the metric's own Phase 2 status
    samples: list[MetricSample] = []  # where to look in the video
    note: str = ""


class SessionComparison(BaseModel):
    """An earlier swim of the same swimmer and whether it may be compared with this one."""

    video_id: str
    analysis_id: str = ""
    recorded_at: str = ""
    compatible: bool
    reasons: list[str] = []  # why not, when not compatible
    synthetic: bool = False  # test fixture, never real progress


class MetricChange(BaseModel):
    """This swim against one compatible earlier swim, for one metric."""

    metric_key: str
    video_id: str
    before: float
    now: float
    unit: str
    threshold: float  # the smallest difference that counts, from resolution and spread
    changed: bool


class Finding(BaseModel):
    """A structured finding. `level` separates what was observed from what may need
    attention; nothing here is a judgement against an outside standard of good technique."""

    id: str  # stable: the same finding gets the same id on every run
    rule_id: str
    level: Literal["observation", "issue_candidate"]
    category: Literal["timing", "body_position", "arm", "history"]
    title: str
    description: str
    metric_keys: list[str] = []
    evidence: list[FindingEvidence] = []
    # "measured": from metrics that passed their own checks. "context_only": from limited
    # metrics or ones kept out of issue detection; shown for information, never a trigger.
    evidence_class: Literal["measured", "context_only"] = "measured"
    context_used: list[str] = []  # personal context that went into it
    changes: list[MetricChange] = []  # comparison with earlier swims, when used
    recurrences: int = 0  # earlier compatible swims in which the same rule also triggered
    limitations: list[str] = []
    actionable: bool = False
    withheld: list[str] = []  # why nothing stronger is said


class PriorityFactor(BaseModel):
    name: str
    points: int
    detail: str


class PriorityCandidate(BaseModel):
    rank: int
    finding_id: str
    title: str
    score: int
    factors: list[PriorityFactor]


class Undetermined(BaseModel):
    """Something that could not be measured or judged, and why. Never a technique problem."""

    key: str
    title: str
    reason: str
    kind: Literal["measurement", "interpretation"] = "measurement"


class RuleStatus(BaseModel):
    """What each issue rule did on this swim, including rules that are not active yet."""

    rule_id: str
    title: str
    state: Literal[
        "triggered", "not_triggered", "suppressed", "not_applicable", "pending_validation"
    ]
    reason: str = ""


class ContextUsed(BaseModel):
    """The personal information that was available. Missing fields are never guessed."""

    swim_level: str | None = None
    personal_best_s: float | None = None  # for this clip's event, when the profile has one
    personal_best_event: str | None = None
    goals: list[str] = []
    primary_goal: str | None = None
    notes: list[str] = []


class ReferenceSwimmer(BaseModel):
    """One strong swimmer's value for a metric, measured by AquaTrack on a public clip."""

    name: str
    group: Literal["sprint", "distance"]
    value: float
    n_cycles: int
    note: str = ""  # who they are, what the clip shows


class ReferenceComparison(BaseModel):
    """The swimmer's value next to strong swimmers filmed the same way. A hint for
    orientation only: never a finding, never ranked, never a fault (owner's decision
    2026-11-18; see docs/REFERENCE_SWIMMERS.md)."""

    metric_key: str
    label: str
    unit: str
    value: float  # the swimmer's
    metric_status: str  # reliable / limited, as measured
    group: Literal["sprint", "distance"]  # which reference swimmers it is set against
    low: float  # range of those swimmers' values
    high: float
    tolerance: float  # differences smaller than this are not told apart
    position: Literal["within", "below", "above"]
    swimmers: list[ReferenceSwimmer] = []
    limitations: list[str] = []


class Interpretation(BaseModel):
    interpretation_version: str = INTERPRETATION_VERSION
    rules_version: str
    video_id: str
    analysis_id: str = ""
    analysis_schema_version: str = ""
    baseline: bool = True  # no compatible earlier swim to compare with
    context: ContextUsed = ContextUsed()
    observations: list[Finding] = []
    issue_candidates: list[Finding] = []
    priorities: list[PriorityCandidate] = []  # at most three; empty is a normal result
    priorities_note: str = ""  # why there are none, or what the ranking rests on
    undetermined: list[Undetermined] = []
    sessions: list[SessionComparison] = []
    rules: list[RuleStatus] = []
    # Added 2026-11-18: strong-swimmer reference hints, kept apart from every finding.
    reference_version: str = ""
    references: list[ReferenceComparison] = []
    summary: str = ""
    created_at: str = Field(default_factory=_now)

    def to_firestore(self) -> dict:
        return json.loads(self.model_dump_json())


# ---------- feedback (Phase 4) ----------
# Built from an Interpretation, the swimmer's goals and the evidence library. Stored as its
# own document per (interpretation, evidence version, goals, explanation source), so older
# feedback is never overwritten and the same inputs give the same document.

FEEDBACK_VERSION = "1.0"


class FeedbackReference(BaseModel):
    """A source from the evidence library, as shown to the swimmer."""

    source_id: str
    citation: str
    url: str
    kind: str  # original_study | review
    population: str
    read: str = "abstract"


class FeedbackItem(BaseModel):
    """One piece of feedback. `category` decides how it may be worded and shown; the
    categories are never mixed:

      observation   measured in this swimmer's video
      focus         a pattern in their own swimming that may deserve attention (not a fault)
      priority      a focus that is also ranked (at most three)
      education     general information for a goal they chose; NOT about their video
      insufficient  something that could not be determined, and what would help
      reference     the swimmer's value next to strong swimmers filmed the same way: a hint
                    for orientation, never a fault, never ranked (added 2026-11-18)
    """

    id: str
    category: Literal["observation", "focus", "priority", "education", "insufficient", "reference"]
    personal: bool  # False for education: it says nothing about this swimmer's swimming
    title: str
    body: str  # deterministic text; always present and always safe to show
    explained: str = ""  # optional reworded text from the language model, validated
    why_it_may_matter: str = ""  # focus / priority: from library claims, with their limits
    finding_id: str = ""  # the interpretation finding it comes from
    metric_keys: list[str] = []
    evidence: list[FindingEvidence] = []  # the measurements, with video timestamps
    claim_ids: list[str] = []  # evidence-library claims it may cite
    goal_keys: list[str] = []
    confidence: Literal["measured", "for_information", "general", "none"] = "none"
    limitations: list[str] = []
    monitor: str = ""  # priority: what could be watched next time
    rank: int | None = None
    factors: list[PriorityFactor] = []


class CheckpointBaseline(BaseModel):
    """A value measured in the video the checkpoint was made from, to compare against later."""

    metric_key: str
    label: str
    value: float
    unit: str


class Checkpoint(BaseModel):
    """Something to look at in the next video. Not a drill, a plan or a promise."""

    id: str
    title: str
    related_item_id: str = ""
    metric_keys: list[str] = []
    # Phase 5: what a later video is compared with, and where the checkpoint came from.
    reason: str = ""
    baseline: list[CheckpointBaseline] = []
    source_video_id: str = ""
    source_analysis_id: str = ""
    created_at: str = ""
    what_to_film: str
    minimum: str = ""  # video length or cycles needed
    compare_with: str = ""
    what_counts_as_a_change: str = ""  # only where a threshold is justified
    limitations: list[str] = []


# ---------- history: comparing sessions (Phase 5) ----------
# Comparisons and progress are computed from stored analysis results each time they are
# asked for. They are never stored as facts of their own, so they cannot go stale or be
# silently rewritten; the analyses they rest on are named in every result.

COMPARISON_VERSION = "1.0"

ChangeState = Literal[
    "increased", "decreased", "no_clear_change", "insufficient_evidence", "not_comparable"
]


class MetricComparison(BaseModel):
    """One metric, an earlier swim against a later one. The words are neutral on purpose:
    "increased" and "decreased" say which way a number moved, never whether that is good."""

    metric_key: str
    label: str
    unit: str = ""
    state: ChangeState
    previous: float | None = None
    current: float | None = None
    change: float | None = None  # current - previous
    relative_pct: float | None = None  # only where a ratio means something
    threshold: float | None = None  # the smallest difference that counts
    previous_status: str = ""
    current_status: str = ""
    previous_cycles: int = 0
    current_cycles: int = 0
    reasons: list[str] = []  # why it is not comparable or the evidence is insufficient
    limitations: list[str] = []


class SessionSummary(BaseModel):
    video_id: str
    analysis_id: str = ""
    recorded_at: str = ""
    stroke: str = ""
    camera: str = ""
    distance: str = ""
    pool_length: str = ""
    schema_version: str = ""
    tracking_grade: str = ""
    view_status: str = ""
    stroke_rate: float | None = None
    synthetic: bool = False


class SessionComparisonResult(BaseModel):
    comparison_version: str = COMPARISON_VERSION
    previous: SessionSummary
    current: SessionSummary
    comparable: bool  # at least one metric could be compared
    session_reasons: list[str] = []  # reasons that rule out every metric
    metrics: list[MetricComparison] = []
    summary: str = ""


class CheckpointFollowUp(BaseModel):
    """What a later video says about a checkpoint from an earlier one. A change is reported
    as a change; it is never called an improvement here."""

    checkpoint_id: str
    title: str
    source_video_id: str = ""
    created_at: str = ""
    state: Literal[
        "not_yet_evaluated",
        "comparable_measurement_available",
        "measurable_change_observed",
        "no_clear_measurable_change",
        "cannot_evaluate",
    ]
    explanation: str = ""
    metrics: list[MetricComparison] = []


class ProgressPoint(BaseModel):
    video_id: str
    recorded_at: str = ""
    value: float
    low: float | None = None
    high: float | None = None
    cycles: int = 0


class ProgressMetric(BaseModel):
    metric_key: str
    label: str
    unit: str = ""
    points: list[ProgressPoint] = []
    # First point against last, when there are at least two: the same neutral states.
    overall: MetricComparison | None = None


class ProgressSeries(BaseModel):
    """Sessions that may be put on one line: same stroke, filming angle, distance and a
    similar effort. Sessions that do not fit start a series of their own."""

    key: str
    stroke: str = ""
    camera: str = ""
    distance: str = ""
    sessions: list[SessionSummary] = []
    metrics: list[ProgressMetric] = []


class Progress(BaseModel):
    progress_version: str = COMPARISON_VERSION
    videos: int = 0  # uploaded
    analyzed: int = 0
    baseline: bool = True  # no two sessions can be compared yet
    series: list[ProgressSeries] = []
    not_in_any_series: list[SessionSummary] = []
    not_included_reasons: dict[str, list[str]] = {}  # video id -> why
    repeated_limitations: list[str] = []
    note: str = ""


class ExplanationInfo(BaseModel):
    source: Literal["template", "llm"] = "template"
    model: str = ""
    note: str = ""  # why the model's text was not used, when it was asked and rejected


class Feedback(BaseModel):
    feedback_version: str = FEEDBACK_VERSION
    evidence_version: str
    rules_version: str
    interpretation_version: str
    video_id: str
    analysis_id: str = ""
    interpretation_id: str = ""
    goals_used: list[str] = []
    primary_goal: str | None = None
    swim_level: str | None = None
    items: list[FeedbackItem] = []
    checkpoints: list[Checkpoint] = []
    references: list[FeedbackReference] = []
    recording_tips: list[str] = []
    # Phase 5: how this video answers the checkpoints of the swimmer's previous video.
    followups: list["CheckpointFollowUp"] = []
    explanation: ExplanationInfo = ExplanationInfo()
    summary: str = ""
    created_at: str = Field(default_factory=_now)

    def to_firestore(self) -> dict:
        return json.loads(self.model_dump_json())


# ---------- problem frames ----------
# Still frames from the swimmer's own video that show what the feedback's priorities rest on.
# Chosen only from the evidence samples (cycles) of the priorities in one Feedback document,
# never for anything the feedback did not report. Stored per feedback document:
# Firestore videos/{id}/frames/{feedbackId}, images in Storage under the analysis folder.

PROBLEM_FRAMES_VERSION = "1.0"


class FrameArrow(BaseModel):
    """An arrow drawn over a frame, from a label to a body point the model placed in it.
    Coordinates are 0-1 of the stored image (the original, unmirrored picture)."""

    joint: str  # e.g. "right wrist"
    to: tuple[float, float]  # the point, from that frame's own pose
    label_at: tuple[float, float]  # where the label sits; the arrow starts there
    label: str  # at most six words


class ProblemFrame(BaseModel):
    item_id: str  # the FeedbackItem (a priority) it illustrates
    finding_id: str = ""
    rank: int | None = None
    t_s: float  # the moment shown
    frame_index: int  # video frame number
    cycle_index: int  # 1-based, among the cycles the analysis measured
    cycle_start_s: float | None = None
    cycle_end_s: float | None = None
    image: str = ""  # Storage path of the JPEG
    width: int = 0
    height: int = 0
    arrows: list[FrameArrow] = []
    joint_confidence: float | None = None  # lowest model confidence of the joints used
    sharpness: float | None = None  # variance of the Laplacian around those joints


class ProblemFrames(BaseModel):
    frames_version: str = PROBLEM_FRAMES_VERSION
    video_id: str
    analysis_id: str = ""
    feedback_id: str = ""
    frames: list[ProblemFrame] = []  # at most five
    # Why there are none: "no_issue" (no priority), "no_frame_rule" (the priority is not
    # something a single frame can show), "no_trusted_frame" (no frame passed the checks).
    empty_reason: Literal["", "no_issue", "no_frame_rule", "no_trusted_frame"] = ""
    created_at: str = Field(default_factory=_now)

    def to_firestore(self) -> dict:
        return json.loads(self.model_dump_json())
