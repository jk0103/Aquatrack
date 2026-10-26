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


# COCO keypoint index for each Joint. COCO's 17 body points are also the first 17 of
# COCO-WholeBody, so every COCO-based backend can use this.
COCO_INDEX = {
    Joint.NOSE: 0,
    Joint.LEFT_SHOULDER: 5,
    Joint.RIGHT_SHOULDER: 6,
    Joint.LEFT_ELBOW: 7,
    Joint.RIGHT_ELBOW: 8,
    Joint.LEFT_WRIST: 9,
    Joint.RIGHT_WRIST: 10,
    Joint.LEFT_HIP: 11,
    Joint.RIGHT_HIP: 12,
    Joint.LEFT_KNEE: 13,
    Joint.RIGHT_KNEE: 14,
    Joint.LEFT_ANKLE: 15,
    Joint.RIGHT_ANKLE: 16,
}


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
