"""Stroke rate (strokes per minute) from wrist motion."""

import numpy as np

from aquatrack.analysis.metrics.signal import fill_gaps, find_peaks, smooth
from aquatrack.analysis.pose.base import Joint, PoseSequence

# No swimmer cycles one arm faster than ~1.5 Hz, so peaks closer than this are noise.
_MAX_CYCLE_HZ = 1.5


def stroke_rate_per_min(pose: PoseSequence, joint: Joint = Joint.RIGHT_WRIST) -> float:
    """Arm cycles per minute for one wrist, using the wrist's vertical position.

    Each peak in the wrist's y track is one full arm cycle for that arm.
    Returns NaN when there is too little tracked data.
    """
    y = fill_gaps(pose.joint(joint)[:, 1])
    if np.isnan(y).all() or len(y) < 3 or pose.fps <= 0:
        return float("nan")
    y = smooth(y, window=max(1, int(pose.fps / 10)))
    peaks = find_peaks(y, min_distance=max(1, int(pose.fps / _MAX_CYCLE_HZ)))
    if len(peaks) < 2:
        return float("nan")
    mean_cycle_frames = np.diff(peaks).mean()
    return float(60.0 * pose.fps / mean_cycle_frames)
