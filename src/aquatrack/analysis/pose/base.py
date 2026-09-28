"""Common pose types shared by every backend (YOLO pose now, fine-tuned models later)."""

from dataclasses import dataclass
from enum import IntEnum
from typing import Protocol

import numpy as np


class Joint(IntEnum):
    """The joints swim metrics need. Backends map their own keypoints onto these."""

    NOSE = 0
    LEFT_SHOULDER = 1
    RIGHT_SHOULDER = 2
    LEFT_ELBOW = 3
    RIGHT_ELBOW = 4
    LEFT_WRIST = 5
    RIGHT_WRIST = 6
    LEFT_HIP = 7
    RIGHT_HIP = 8
    LEFT_KNEE = 9
    RIGHT_KNEE = 10
    LEFT_ANKLE = 11
    RIGHT_ANKLE = 12


@dataclass
class PoseSequence:
    """Keypoints over time.

    `keypoints` has shape (frames, len(Joint), 3): normalized x, y and a 0-1 confidence.
    Frames where the swimmer was not detected are NaN.
    """

    keypoints: np.ndarray
    fps: float

    def joint(self, joint: Joint) -> np.ndarray:
        """(frames, 3) track for one joint."""
        return self.keypoints[:, joint, :]


class PoseEstimator(Protocol):
    def estimate(self, video_path: str, step: int = 1) -> PoseSequence: ...
