"""Reading swim videos frame by frame."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    fps: float
    frame_count: int

    @property
    def duration_s(self) -> float:
        return self.frame_count / self.fps if self.fps else 0.0


def _open(path: str | Path) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {path}")
    return cap


def read_video_info(path: str | Path) -> VideoInfo:
    cap = _open(path)
    try:
        return VideoInfo(
            width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            fps=float(cap.get(cv2.CAP_PROP_FPS)),
            frame_count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        )
    finally:
        cap.release()


def iter_frames(path: str | Path, step: int = 1) -> Iterator[tuple[int, np.ndarray]]:
    """Yield (frame_index, BGR frame) for every `step`-th frame."""
    if step < 1:
        raise ValueError("step must be >= 1")
    cap = _open(path)
    try:
        index = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if index % step == 0:
                yield index, frame
            index += 1
    finally:
        cap.release()
