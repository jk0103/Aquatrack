"""Whole-body pose: all 133 COCO-WholeBody points (body, feet, face, hands) over time.

Layout of the 133 points:
  0-16    body, in COCO order (so `COCO_INDEX` maps them onto `Joint`)
  17-19   left foot: big toe, small toe, heel; 20-22 right foot
  23-90   face (68 points; kept in the data but not drawn or used yet)
  91-111  left hand: wrist, then 4 points per finger from thumb to pinky; 112-132 right hand
"Left" and "right" are the swimmer's own sides.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from aquatrack.analysis.pose.base import COCO_INDEX, Joint, PoseSequence

NUM_KEYPOINTS = 133

BODY = range(0, 17)
LEFT_FOOT = range(17, 20)
RIGHT_FOOT = range(20, 23)
FACE = range(23, 91)
LEFT_HAND = range(91, 112)
RIGHT_HAND = range(112, 133)

# A point counts as found at or above this score. RTMW scores are SimCC peak heights, not
# 0-1 probabilities: stock RTMW-x gives ~4-8 on clear underwater frames, and points scoring
# under ~3 were visibly wrong on our sample clip. A first cut, to revisit in cleanup.
MIN_SCORE = 3.0


def _hand_edges(wrist: int) -> list[tuple[int, int]]:
    edges = []
    for finger in range(5):
        base = wrist + 1 + 4 * finger
        edges += [(wrist, base), (base, base + 1), (base + 1, base + 2), (base + 2, base + 3)]
    return edges


# Lines drawn for the skeleton: body, feet and hands (no face).
SKELETON: list[tuple[int, int]] = [
    # head
    (0, 1), (0, 2), (1, 3), (2, 4), (3, 5), (4, 6),
    # arms and torso
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11), (6, 12), (11, 12),
    # legs
    (11, 13), (13, 15), (12, 14), (14, 16),
    # feet: ankle to big toe, small toe, heel
    (15, 17), (15, 18), (15, 19), (16, 20), (16, 21), (16, 22),
    # body wrist to hand wrist
    (9, LEFT_HAND[0]), (10, RIGHT_HAND[0]),
    *_hand_edges(LEFT_HAND[0]),
    *_hand_edges(RIGHT_HAND[0]),
]  # fmt: skip

LEFT_POINTS = frozenset([*range(1, 17, 2), *LEFT_FOOT, *LEFT_HAND])
RIGHT_POINTS = frozenset([*range(2, 17, 2), *RIGHT_FOOT, *RIGHT_HAND])


def side(index: int) -> str:
    """'left', 'right' or 'center' for a keypoint index."""
    if index in LEFT_POINTS:
        return "left"
    if index in RIGHT_POINTS:
        return "right"
    return "center"


def edge_side(a: int, b: int) -> str:
    """Side of a skeleton line: left/right when both ends agree, else center."""
    sa, sb = side(a), side(b)
    return sa if sa == sb else "center"


def default_pose_path(video_path: str | Path) -> Path:
    """Where a video's whole-body pose is saved: next to the video."""
    video_path = Path(video_path)
    return video_path.with_name(f"{video_path.stem}.wholebody.npz")


@dataclass
class WholeBodySequence:
    """133 whole-body keypoints over time.

    `keypoints` has shape (frames, 133, 3): x and y normalized to the frame size, and the
    model's score. Frames with no swimmer are NaN. `frame_indices` are the source video
    frames that were analyzed (every `step`-th frame), and `fps` is their rate.
    """

    keypoints: np.ndarray
    fps: float
    frame_indices: np.ndarray
    width: int
    height: int
    model: str = ""

    def __len__(self) -> int:
        return len(self.keypoints)

    def points(self, indices: range | list[int]) -> np.ndarray:
        """(frames, len(indices), 3) track for a group such as LEFT_HAND."""
        return self.keypoints[:, list(indices), :]

    def found(self, indices: range | list[int], min_score: float = MIN_SCORE) -> np.ndarray:
        """Per frame, whether at least half of a group's points scored `min_score` or more."""
        scores = self.points(indices)[:, :, 2]
        with np.errstate(invalid="ignore"):
            hits = (scores >= min_score).sum(axis=1)
        return hits * 2 >= len(indices)

    def has_swimmer(self) -> np.ndarray:
        """Per frame, whether a swimmer box was found (keypoints not NaN)."""
        return ~np.isnan(self.keypoints[:, 0, 0])

    def to_pose_sequence(self) -> PoseSequence:
        """The 13 `Joint` body points, for metrics such as stroke rate and symmetry."""
        keypoints = np.full((len(self), len(Joint), 3), np.nan)
        for joint, coco_index in COCO_INDEX.items():
            keypoints[:, joint] = self.keypoints[:, coco_index]
        return PoseSequence(keypoints=keypoints, fps=self.fps)

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        np.savez_compressed(
            path,
            keypoints=self.keypoints.astype(np.float32),
            fps=self.fps,
            frame_indices=self.frame_indices,
            width=self.width,
            height=self.height,
            model=self.model,
        )
        return path

    @classmethod
    def load(cls, path: str | Path) -> "WholeBodySequence":
        with np.load(path) as data:
            return cls(
                keypoints=data["keypoints"].astype(np.float64),
                fps=float(data["fps"]),
                frame_indices=data["frame_indices"],
                width=int(data["width"]),
                height=int(data["height"]),
                model=str(data["model"]),
            )
