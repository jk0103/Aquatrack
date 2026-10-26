"""RTMW whole-body pose backend (133 points). Needs the optional extra: `uv sync --extra pose`.

Two stages per frame: a YOLO model finds the swimmer's box (the largest person), then
RTMW-x, run through rtmlib on onnxruntime, places 133 keypoints inside that box.
"""

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

from aquatrack.analysis.pose.base import PoseSequence
from aquatrack.analysis.pose.wholebody import NUM_KEYPOINTS, WholeBodySequence
from aquatrack.analysis.pose.yolo_backend import DEFAULT_MODEL as STOCK_YOLO
from aquatrack.analysis.video import iter_frames, read_video_info

MODELS_DIR = Path(os.environ.get("AQUATRACK_MODELS_DIR", "models"))
# Official RTMW-x 384x288 (COCO-WholeBody), exported to ONNX by the training notebook.
# Not in git: download MyDrive/aquatrack_swim_full/rtmw/rtmw_x_stock.onnx into models/.
RTMW_ONNX = MODELS_DIR / "rtmw_x_stock.onnx"
# Our swim-trained YOLO; it finds swimmers underwater far more reliably than stock YOLO.
SWIM_DETECTOR = MODELS_DIR / "swim_pose.pt"

RTMW_INPUT_SIZE = (288, 384)  # width, height

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


class YoloPersonDetector:
    """Person boxes from a YOLO model: our swim model if present, else stock YOLO."""

    def __init__(
        self,
        model: str | Path | None = None,
        min_confidence: float = 0.25,
        device: str | None = None,
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

    def __call__(self, frame_bgr: np.ndarray) -> np.ndarray:
        result = self._model.predict(
            frame_bgr,
            conf=self._min_confidence,
            classes=[0],
            device=self._device,
            verbose=False,
        )[0]
        return result.boxes.xyxy.cpu().numpy()


@dataclass
class RunStats:
    """Wall-clock time of the last run, split by stage."""

    frames: int = 0
    detect_s: float = 0.0
    pose_s: float = 0.0
    timings: list[float] = field(default_factory=list, repr=False)

    @property
    def seconds_per_frame(self) -> float:
        return (self.detect_s + self.pose_s) / self.frames if self.frames else float("nan")


class RtmwEstimator:
    """Whole-body pose for the largest person in each analyzed frame.

    `estimate` returns the 13-joint `PoseSequence` like the other backends;
    `estimate_wholebody` keeps all 133 points.
    """

    def __init__(
        self,
        onnx_path: str | Path = RTMW_ONNX,
        detector: PersonDetector | None = None,
        device: str = "cpu",
        pose_model: PoseModel | None = None,
    ):
        if pose_model is None:
            onnx_path = Path(onnx_path)
            if not onnx_path.exists():
                raise FileNotFoundError(
                    f"RTMW model not found at {onnx_path}. Download rtmw_x_stock.onnx from "
                    "Google Drive (MyDrive/aquatrack_swim_full/rtmw/) into models/."
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
        self.model_name = Path(onnx_path).name
        self._pose_model = pose_model
        self._detector = detector if detector is not None else YoloPersonDetector()
        self.last_run = RunStats()

    def estimate_frame(self, frame_bgr: np.ndarray) -> np.ndarray:
        """(133, 3) normalized x, y and score for one frame; NaN when no swimmer is found."""
        height, width = frame_bgr.shape[:2]
        points = np.full((NUM_KEYPOINTS, 3), np.nan)

        start = time.perf_counter()
        box = largest_box(self._detector(frame_bgr))
        detected = time.perf_counter()
        if box is not None:
            # RTMW was trained on RGB; rtmlib's own pipeline would hand it BGR.
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            kpts, scores = self._pose_model(rgb, bboxes=[box.tolist()])
            points[:, 0] = kpts[0, :, 0] / width
            points[:, 1] = kpts[0, :, 1] / height
            points[:, 2] = scores[0]
        done = time.perf_counter()

        stats = self.last_run
        stats.frames += 1
        stats.detect_s += detected - start
        stats.pose_s += done - detected
        stats.timings.append(done - start)
        return points

    def estimate_wholebody(self, video_path: str | Path, step: int = 1) -> WholeBodySequence:
        info = read_video_info(video_path)
        self.last_run = RunStats()
        indices, frames = [], []
        for index, frame in iter_frames(video_path, step=step):
            indices.append(index)
            frames.append(self.estimate_frame(frame))
        keypoints = np.stack(frames) if frames else np.empty((0, NUM_KEYPOINTS, 3))
        return WholeBodySequence(
            keypoints=keypoints,
            fps=info.fps / step,
            frame_indices=np.array(indices, dtype=np.int64),
            width=info.width,
            height=info.height,
            model=self.model_name,
        )

    def estimate(self, video_path: str, step: int = 1) -> PoseSequence:
        return self.estimate_wholebody(video_path, step=step).to_pose_sequence()
