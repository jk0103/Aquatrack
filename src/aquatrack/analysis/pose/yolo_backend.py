"""Ultralytics YOLO pose backend. Needs the optional extra: `uv sync --extra pose`.

Uses COCO's 17 keypoints. Good enough to prototype on deck/overhead video; expect dropped
frames underwater (bubbles, refraction, body cut by the surface line) until the model is
fine-tuned on labeled swim frames. Weights download on first use.
"""

import numpy as np

from aquatrack.analysis.pose.base import COCO_INDEX, Joint, PoseSequence
from aquatrack.analysis.video import iter_frames, read_video_info

DEFAULT_MODEL = "yolo26n-pose.pt"


def select_swimmer(xyn: np.ndarray, conf: np.ndarray | None, boxes_xywhn: np.ndarray) -> np.ndarray:
    """Pick the largest detected person and map their keypoints onto `Joint`.

    Pools often have other swimmers or people on deck in frame; the one being filmed
    is usually the biggest. Returns a (len(Joint), 3) array of x, y, confidence,
    all NaN when nobody was detected.
    """
    points = np.full((len(Joint), 3), np.nan)
    if len(boxes_xywhn) == 0:
        return points
    person = int(np.argmax(boxes_xywhn[:, 2] * boxes_xywhn[:, 3]))
    for joint, coco_index in COCO_INDEX.items():
        x, y = xyn[person, coco_index]
        c = 1.0 if conf is None else conf[person, coco_index]
        points[joint] = (x, y, c)
    return points


class YoloPoseEstimator:
    def __init__(self, model: str = DEFAULT_MODEL, min_confidence: float = 0.25):
        try:
            from ultralytics import YOLO
        except ImportError as e:
            raise ImportError("Install the pose extra: uv sync --extra pose") from e
        self._model = YOLO(model)
        self._min_confidence = min_confidence

    def estimate(self, video_path: str, step: int = 1) -> PoseSequence:
        info = read_video_info(video_path)
        frames = []
        for _, frame in iter_frames(video_path, step=step):
            result = self._model.predict(frame, conf=self._min_confidence, verbose=False)[0]
            kp = result.keypoints
            frames.append(
                select_swimmer(
                    xyn=kp.xyn.cpu().numpy(),
                    conf=None if kp.conf is None else kp.conf.cpu().numpy(),
                    boxes_xywhn=result.boxes.xywhn.cpu().numpy(),
                )
            )
        keypoints = np.stack(frames) if frames else np.empty((0, len(Joint), 3))
        return PoseSequence(keypoints=keypoints, fps=info.fps / step)
