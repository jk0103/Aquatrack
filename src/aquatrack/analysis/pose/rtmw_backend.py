"""RTMW whole-body pose backend (133 points). Needs the optional extra: `uv sync --extra pose`.

Two stages per frame: a YOLO model finds the people in the frame and one of them is kept as
the target swimmer (by tracking: the box that continues the previous one), then RTMW-x, run
through rtmlib on onnxruntime, places 133 keypoints inside that box.
"""

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

from aquatrack.analysis.pose.base import PoseSequence
from aquatrack.analysis.pose.wholebody import BODY, MIN_SCORE, NUM_KEYPOINTS, WholeBodySequence
from aquatrack.analysis.pose.yolo_backend import DEFAULT_MODEL as STOCK_YOLO
from aquatrack.analysis.video import file_sha256, iter_frames, read_video_info
from aquatrack.contracts import (
    BoxSource,
    ModelConfig,
    ModelInfo,
    Provenance,
    RawPose,
    RawPoseMeta,
    Selection,
    VideoIdentity,
)

MODELS_DIR = Path(os.environ.get("AQUATRACK_MODELS_DIR", "models"))
# Official RTMW-x 384x288 (cocktail14 checkpoint) exported to ONNX. Not in git and never
# fetched at run time: a worker image gets it at build time from the public checkpoint
# (analysis/pose/manifest.py, docs/INFERENCE_WORKER.md).
RTMW_ONNX = MODELS_DIR / "rtmw_x_stock.onnx"
# Our swim-trained YOLO; it finds swimmers underwater far more reliably than stock YOLO.
SWIM_DETECTOR = MODELS_DIR / "swim_pose.pt"

RTMW_INPUT_SIZE = (288, 384)  # width, height
BODY_POINTS = list(BODY)
# How long a swimmer box is carried forward through detector misses.
MAX_BOX_CARRY_S = 0.5

# CoreML settings for device="mps". The MLProgram format keeps full precision and matches
# CPU output; rtmlib's own "mps" uses the older fp16 format, which put whole frames of
# keypoints hundreds of pixels off on our sample clip.
_COREML_OPTIONS = {"ModelFormat": "MLProgram", "MLComputeUnits": "CPUAndGPU"}


class PersonDetector(Protocol):
    def __call__(self, frame_bgr: np.ndarray) -> np.ndarray:
        """(N, 4) person boxes as x1, y1, x2, y2 in pixels."""
        ...


class PoseModel(Protocol):
    def __call__(self, image: np.ndarray, bboxes: list) -> tuple[np.ndarray, np.ndarray]:
        """Keypoints (people, 133, 2) in pixels and scores (people, 133)."""
        ...


def largest_box(boxes: np.ndarray) -> np.ndarray | None:
    """The biggest box, which is usually the swimmer being filmed; None if there are none."""
    if len(boxes) == 0:
        return None
    areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    return boxes[int(np.argmax(areas))]


def box_iou(a: np.ndarray, b: np.ndarray) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - ix * iy
    return float(ix * iy / union) if union > 0 else 0.0


def box_center(box: np.ndarray) -> np.ndarray:
    return np.array([(box[0] + box[2]) / 2, (box[1] + box[3]) / 2])


# A detected box continues the previous one when they overlap at least this much.
MIN_TRACK_IOU = 0.1


def select_target(
    detections: np.ndarray, previous: np.ndarray | None, mode: str = "tracking"
) -> tuple[np.ndarray | None, Selection]:
    """Pick the target swimmer among `detections` (N, 5: x1, y1, x2, y2, confidence).

    tracking: the box overlapping the previous target most; with no overlap, the nearest
    one; with no previous target, the largest area x confidence. Pools have other swimmers,
    people on deck and mirror images on the surface, and the largest box is not always the
    swimmer being filmed. `largest` is the older rule, kept for comparison.
    Returns the chosen row and how it was chosen.
    """
    if len(detections) == 0:
        return None, Selection.NONE
    boxes = detections[:, :4]
    areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    if mode == "largest":
        return detections[int(np.argmax(areas))], Selection.LARGEST
    if previous is None:
        confidence = np.nan_to_num(detections[:, 4], nan=1.0)
        return detections[int(np.argmax(areas * confidence))], Selection.FIRST
    overlaps = np.array([box_iou(b, previous) for b in boxes])
    best = int(np.argmax(overlaps))
    if overlaps[best] > MIN_TRACK_IOU:
        return detections[best], Selection.OVERLAP
    distances = np.linalg.norm(
        np.array([box_center(b) for b in boxes]) - box_center(previous), axis=1
    )
    return detections[int(np.argmin(distances))], Selection.NEAREST


@dataclass
class FrameRecord:
    """What happened in one analysed frame, kept for the raw pose file."""

    box: np.ndarray | None = None
    confidence: float = float("nan")
    source: BoxSource = BoxSource.NONE
    selection: Selection = Selection.NONE
    candidates: int = 0


class BoxTracker:
    """Keeps a swimmer box through detector misses.

    The detector misses the swimmer in many frames when splash or the surface hides most
    of the body (above-water side views are worst). The swimmer moves smoothly, so for a
    short while we carry the last box forward at its recent speed and let RTMW's scores
    decide whether the swimmer is really there.

    Only the box's position is carried: its size stays as last detected. Detected boxes can
    change shape a lot from one frame to the next (an arm leaving the water, a reflection
    joined on), and extrapolating that change made carried boxes grow past the frame on a
    real clip.
    """

    def __init__(self, max_missing: int):
        self.max_missing = max_missing
        self.last: np.ndarray | None = None
        self.velocity = np.zeros(4)
        self.missing = 0

    def update(self, box: np.ndarray | None) -> tuple[np.ndarray | None, bool]:
        """The box to use this frame, and whether it was carried rather than detected."""
        if box is not None:
            if self.last is not None and self.missing == 0:
                shift = (box[:2] + box[2:] - self.last[:2] - self.last[2:]) / 2  # centre move
                self.velocity = np.concatenate([shift, shift])
            elif self.last is None:
                self.velocity = np.zeros(4)
            self.last, self.missing = box, 0
            return box, False
        if self.last is None or self.missing >= self.max_missing:
            return None, False
        self.missing += 1
        return self.last + self.velocity * self.missing, True

    def lost(self) -> None:
        """RTMW found no body in a carried box: stop carrying it."""
        self.last = None


class YoloPersonDetector:
    """Person boxes from a YOLO model: our swim model if present, else stock YOLO."""

    def __init__(
        self,
        model: str | Path | None = None,
        min_confidence: float = 0.25,
        device: str | None = None,
        imgsz: int | None = None,
    ):
        try:
            from ultralytics import YOLO
        except ImportError as e:
            raise ImportError("Install the pose extra: uv sync --extra pose") from e
        if model is None:
            model = SWIM_DETECTOR if SWIM_DETECTOR.exists() else STOCK_YOLO
        self.name = Path(model).name
        self._model = YOLO(str(model))
        self._min_confidence = min_confidence
        self._device = device
        self._imgsz = imgsz

    @classmethod
    def from_config(
        cls, config: ModelConfig, device: str | None = None, offline: bool = False
    ) -> "YoloPersonDetector":
        """The detector a `ModelConfig` names. A bare file name is looked up in the models
        folder first. If it is not there, Ultralytics would download pretrained weights by
        itself: fine on a developer's machine, never in a worker, so `offline` refuses."""
        weights = Path(config.detector_weights)
        if not weights.is_absolute() and (MODELS_DIR / weights).exists():
            weights = MODELS_DIR / weights
        elif offline:
            raise FileNotFoundError(f"Detector weights {weights.name} are not installed.")
        return cls(
            weights,
            min_confidence=config.detector_confidence,
            device=device,
            imgsz=config.detector_imgsz,
        )

    def detect(self, frame_bgr: np.ndarray) -> np.ndarray:
        """(N, 5) person boxes: x1, y1, x2, y2 in pixels and the detector's confidence."""
        options = {} if self._imgsz is None else {"imgsz": self._imgsz}
        result = self._model.predict(
            frame_bgr,
            conf=self._min_confidence,
            classes=[0],
            device=self._device,
            verbose=False,
            **options,
        )[0]
        return result.boxes.data[:, :5].cpu().numpy()

    def __call__(self, frame_bgr: np.ndarray) -> np.ndarray:
        return self.detect(frame_bgr)[:, :4]


@dataclass
class RunStats:
    """Wall-clock time of the last run, split by stage."""

    frames: int = 0
    carried: int = 0  # frames posed from a carried box (detector missed)
    detect_s: float = 0.0
    pose_s: float = 0.0
    timings: list[float] = field(default_factory=list, repr=False)

    @property
    def seconds_per_frame(self) -> float:
        return (self.detect_s + self.pose_s) / self.frames if self.frames else float("nan")


class RtmwEstimator:
    """Whole-body pose for the target swimmer in each analyzed frame.

    `estimate` returns the 13-joint `PoseSequence` like the other backends;
    `estimate_wholebody` keeps all 133 points; `estimate_raw` returns the versioned
    `RawPose` with boxes, selection and model details for every frame.
    """

    def __init__(
        self,
        onnx_path: str | Path = RTMW_ONNX,
        detector: PersonDetector | None = None,
        device: str = "cpu",
        pose_model: PoseModel | None = None,
        target_selection: str = "tracking",
    ):
        self._onnx_path: Path | None = None
        if pose_model is None:
            onnx_path = Path(onnx_path)
            if not onnx_path.exists():
                raise FileNotFoundError(
                    f"RTMW model {onnx_path.name} is not installed in the models folder. "
                    "See docs/INFERENCE_WORKER.md for how a worker image gets it."
                )
            try:
                from rtmlib import RTMPose
            except ImportError as e:
                raise ImportError("Install the pose extra: uv sync --extra pose") from e
            pose_model = RTMPose(
                str(onnx_path),
                model_input_size=RTMW_INPUT_SIZE,
                backend="onnxruntime",
                device="cpu" if device == "mps" else device,
            )
            if device == "mps":
                import onnxruntime as ort

                # rtmlib can't take provider options, so swap in our own session.
                providers = [("CoreMLExecutionProvider", _COREML_OPTIONS), "CPUExecutionProvider"]
                pose_model.session = ort.InferenceSession(str(onnx_path), providers=providers)
            self._onnx_path = onnx_path
        self.model_name = Path(onnx_path).name
        self._pose_model = pose_model
        self._detector = detector if detector is not None else YoloPersonDetector()
        self.last_run = RunStats()
        self._tracker: BoxTracker | None = None  # set per video by estimate_wholebody
        self._target_selection = target_selection
        self._previous_target: np.ndarray | None = None
        self.last_frames: list[FrameRecord] = []
        self.max_box_carry_s = MAX_BOX_CARRY_S

    def _detect(self, frame_bgr: np.ndarray) -> np.ndarray:
        """(N, 5) boxes with confidence; detectors that only return boxes get NaN scores."""
        if hasattr(self._detector, "detect"):
            return np.asarray(self._detector.detect(frame_bgr), dtype=float).reshape(-1, 5)
        boxes = np.asarray(self._detector(frame_bgr), dtype=float).reshape(-1, 4)
        return np.hstack([boxes, np.full((len(boxes), 1), np.nan)])

    def estimate_frame(self, frame_bgr: np.ndarray) -> np.ndarray:
        """(133, 3) normalized x, y and score for one frame; NaN when no swimmer is found."""
        height, width = frame_bgr.shape[:2]
        points = np.full((NUM_KEYPOINTS, 3), np.nan)

        stats = self.last_run
        start = time.perf_counter()
        detections = self._detect(frame_bgr)
        picked, how = select_target(detections, self._previous_target, self._target_selection)
        record = FrameRecord(candidates=len(detections))
        box = None if picked is None else picked[:4]
        carried = False
        if self._tracker is not None:
            box, carried = self._tracker.update(box)
        if picked is not None:
            self._previous_target = picked[:4]
            record.confidence = float(picked[4])
        elif box is None:
            self._previous_target = None  # track ended; the next box starts a new one
        detected = time.perf_counter()
        if box is not None:
            # RTMW was trained on RGB; rtmlib's own pipeline would hand it BGR.
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            kpts, scores = self._pose_model(rgb, bboxes=[box.tolist()])
            if carried and np.median(scores[0, BODY_POINTS]) < MIN_SCORE:
                self._tracker.lost()  # nobody there: don't invent a pose
                self._previous_target = None
            else:
                points[:, 0] = kpts[0, :, 0] / width
                points[:, 1] = kpts[0, :, 1] / height
                points[:, 2] = scores[0]
                stats.carried += carried
                record.box = np.asarray(box, dtype=float)
                record.source = BoxSource.CARRIED if carried else BoxSource.DETECTED
                record.selection = Selection.CARRIED if carried else how
        self.last_frames.append(record)
        done = time.perf_counter()

        stats.frames += 1
        stats.detect_s += detected - start
        stats.pose_s += done - detected
        stats.timings.append(done - start)
        return points

    def estimate_wholebody(
        self, video_path: str | Path, step: int = 1, on_frame=None
    ) -> WholeBodySequence:
        """`on_frame(done, total)` is called after every analysed frame. It may raise to
        stop the run (a cancelled job, a lost lease, a time or memory limit)."""
        info = read_video_info(video_path)
        total = max(1, -(-info.frame_count // step))
        self.last_run = RunStats()
        self._tracker = BoxTracker(max(1, round(self.max_box_carry_s * info.fps / step)))
        self._previous_target = None
        self.last_frames = []
        indices, frames = [], []
        for index, frame in iter_frames(video_path, step=step):
            indices.append(index)
            frames.append(self.estimate_frame(frame))
            if on_frame is not None:
                on_frame(len(frames), total)
        keypoints = np.stack(frames) if frames else np.empty((0, NUM_KEYPOINTS, 3))
        return WholeBodySequence(
            keypoints=keypoints,
            fps=info.fps / step,
            frame_indices=np.array(indices, dtype=np.int64),
            width=info.width,
            height=info.height,
            model=self.model_name,
        )

    def estimate_raw(
        self,
        video_path: str | Path,
        config: ModelConfig | None = None,
        video_id: str | None = None,
        source: str = "local",
        produced_by: str = "aquatrack",
        on_frame=None,
    ) -> RawPose:
        """Run detection and pose on a video and return the versioned raw output."""
        config = config or ModelConfig()
        self._target_selection = config.target_selection
        self.max_box_carry_s = config.max_box_carry_s
        seq = self.estimate_wholebody(video_path, step=config.frame_step, on_frame=on_frame)
        records = self.last_frames
        n = len(seq)
        info = read_video_info(video_path)
        decoded = int(seq.frame_indices[-1]) + 1 if n else 0  # frames actually read
        boxes = np.full((n, 4), np.nan)
        for i, r in enumerate(records):
            if r.box is not None:
                boxes[i] = r.box
        detector_name = getattr(self._detector, "name", type(self._detector).__name__)
        return RawPose(
            meta=RawPoseMeta(
                video=VideoIdentity(
                    sha256=file_sha256(video_path),
                    frame_count=decoded,
                    fps=info.fps,
                    width=seq.width,
                    height=seq.height,
                ),
                video_id=video_id,
                fps=seq.fps,
                width=seq.width,
                height=seq.height,
                config=config,
                detector=ModelInfo(name=detector_name),
                pose=ModelInfo(
                    name=self.model_name,
                    sha256=file_sha256(self._onnx_path) if self._onnx_path else None,
                ),
                provenance=Provenance(source=source, produced_by=produced_by),
            ),
            frame_indices=seq.frame_indices,
            timestamps_s=seq.frame_indices / info.fps,
            keypoints=seq.keypoints,
            boxes=boxes,
            box_confidence=np.array([r.confidence for r in records], dtype=float),
            box_source=np.array([int(r.source) for r in records], dtype=np.uint8),
            selection=np.array([int(r.selection) for r in records], dtype=np.uint8),
            candidates=np.array([r.candidates for r in records], dtype=np.int16),
        )

    def estimate(self, video_path: str, step: int = 1) -> PoseSequence:
        return self.estimate_wholebody(video_path, step=step).to_pose_sequence()
