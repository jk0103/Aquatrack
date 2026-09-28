import numpy as np
import pytest

from aquatrack.analysis.metrics import arm_symmetry, stroke_rate_per_min
from aquatrack.analysis.pose import Joint, PoseSequence


def synthetic_pose(
    cycles_per_min: float,
    fps: float = 30.0,
    seconds: float = 20.0,
    left_amp: float = 0.2,
    right_amp: float = 0.2,
) -> PoseSequence:
    """Wrists moving up and down like a steady arm stroke, arms half a cycle apart."""
    t = np.arange(int(fps * seconds)) / fps
    freq = cycles_per_min / 60.0
    keypoints = np.full((len(t), len(Joint), 3), 0.5)
    keypoints[:, Joint.RIGHT_WRIST, 1] = 0.5 + right_amp * np.sin(2 * np.pi * freq * t)
    keypoints[:, Joint.LEFT_WRIST, 1] = 0.5 + left_amp * np.sin(2 * np.pi * freq * t + np.pi)
    return PoseSequence(keypoints=keypoints, fps=fps)


@pytest.mark.parametrize("rate", [30.0, 45.0, 60.0])
def test_stroke_rate(rate):
    assert stroke_rate_per_min(synthetic_pose(rate)) == pytest.approx(rate, rel=0.05)


def test_stroke_rate_survives_dropped_frames():
    pose = synthetic_pose(40.0)
    pose.keypoints[::7, Joint.RIGHT_WRIST, :] = np.nan
    assert stroke_rate_per_min(pose) == pytest.approx(40.0, rel=0.05)


def test_stroke_rate_nan_without_tracking():
    pose = synthetic_pose(40.0)
    pose.keypoints[:, Joint.RIGHT_WRIST, :] = np.nan
    assert np.isnan(stroke_rate_per_min(pose))


def test_symmetry_balanced():
    assert arm_symmetry(synthetic_pose(40.0)) == pytest.approx(1.0, rel=0.01)


def test_symmetry_weak_left_arm():
    pose = synthetic_pose(40.0, left_amp=0.1, right_amp=0.2)
    assert arm_symmetry(pose) == pytest.approx(0.5, rel=0.02)
