"""Left-right balance of the arm stroke."""

import numpy as np

from aquatrack.analysis.metrics.signal import fill_gaps
from aquatrack.analysis.pose.base import Joint, PoseSequence


def _vertical_range(pose: PoseSequence, joint: Joint) -> float:
    y = fill_gaps(pose.joint(joint)[:, 1])
    if np.isnan(y).all():
        return float("nan")
    return float(np.percentile(y, 95) - np.percentile(y, 5))


def arm_symmetry(pose: PoseSequence) -> float:
    """Ratio of left to right wrist travel, 1.0 = perfectly balanced.

    Values below 1 mean the left arm moves less than the right; above 1 the opposite.
    """
    left = _vertical_range(pose, Joint.LEFT_WRIST)
    right = _vertical_range(pose, Joint.RIGHT_WRIST)
    if np.isnan(left) or np.isnan(right) or right == 0:
        return float("nan")
    return left / right
