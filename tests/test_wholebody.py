from pathlib import Path

import cv2
import numpy as np
import pytest

from aquatrack.analysis.pose import Joint
from aquatrack.analysis.pose.cli import coverage
from aquatrack.analysis.pose.overlay import draw_skeleton, render_overlay
from aquatrack.analysis.pose.rtmw_backend import RtmwEstimator, largest_box
from aquatrack.analysis.pose.wholebody import (
    LEFT_HAND,
    MIN_SCORE,
    NUM_KEYPOINTS,
    RIGHT_FOOT,
    WholeBodySequence,
    default_pose_path,
    edge_side,
    side,
)

GOOD = MIN_SCORE + 1


class FakeDetector:
    """One box on even calls, none on odd calls."""

    def __init__(self):
        self.calls = 0

    def __call__(self, frame_bgr):
        self.calls += 1
        if self.calls % 2 == 0:
            return np.empty((0, 4))
        return np.array([[0, 0, 10, 10], [8.0, 4.0, 40.0, 36.0]])  # small, then the swimmer


class FakePoseModel:
    """Puts every keypoint at the box center, and records the images it was given."""

    def __init__(self):
        self.images = []

    def __call__(self, image, bboxes):
        self.images.append(image)
        x1, y1, x2, y2 = bboxes[0]
        kpts = np.tile([(x1 + x2) / 2, (y1 + y2) / 2], (1, NUM_KEYPOINTS, 1))
        return kpts, np.full((1, NUM_KEYPOINTS), GOOD)


@pytest.fixture
def blue_video(tmp_path: Path) -> Path:
    """10 frames of pure blue (BGR) at 10 fps, 64x48."""
    path = tmp_path / "blue.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (64, 48))
    for _ in range(10):
        writer.write(np.full((48, 64, 3), (255, 0, 0), dtype=np.uint8))
    writer.release()
    return path


def make_sequence(frames: int = 4) -> WholeBodySequence:
    keypoints = np.random.default_rng(0).random((frames, NUM_KEYPOINTS, 3))
    keypoints[:, :, 2] = GOOD
    keypoints[1] = np.nan
    return WholeBodySequence(
        keypoints=keypoints,
        fps=5.0,
        frame_indices=np.arange(0, 2 * frames, 2),
        width=64,
        height=48,
        model="fake.onnx",
    )


def test_largest_box():
    boxes = np.array([[0, 0, 10, 10], [5, 5, 50, 30], [0, 0, 20, 20]])
    assert largest_box(boxes).tolist() == [5, 5, 50, 30]
    assert largest_box(np.empty((0, 4))) is None


def test_estimate_wholebody_with_fake_models(blue_video):
    pose_model = FakePoseModel()
    estimator = RtmwEstimator(detector=FakeDetector(), pose_model=pose_model)

    pose = estimator.estimate_wholebody(blue_video, step=2)

    assert pose.keypoints.shape == (5, NUM_KEYPOINTS, 3)
    assert pose.frame_indices.tolist() == [0, 2, 4, 6, 8]
    assert pose.fps == pytest.approx(5.0)
    assert (pose.width, pose.height) == (64, 48)
    # The detector finds the swimmer on frames 0, 4, 8 only.
    assert pose.has_swimmer().tolist() == [True, False, True, False, True]
    # Keypoints sit at the larger box's center, normalized to the frame size.
    np.testing.assert_allclose(pose.keypoints[0, :, :2], np.tile([24 / 64, 20 / 48], (133, 1)))
    # The pose model gets RGB: blue lands in the last channel.
    assert pose_model.images[0][0, 0, 2] > 200 and pose_model.images[0][0, 0, 0] < 50
    assert estimator.last_run.frames == 5


def test_estimate_returns_joint_sequence(blue_video):
    estimator = RtmwEstimator(detector=FakeDetector(), pose_model=FakePoseModel())
    pose = estimator.estimate(str(blue_video))
    assert pose.keypoints.shape == (10, len(Joint), 3)
    assert pose.fps == pytest.approx(10.0)


def test_missing_onnx_file_says_where_to_get_it(tmp_path):
    with pytest.raises(FileNotFoundError, match="Google Drive"):
        RtmwEstimator(tmp_path / "missing.onnx", detector=FakeDetector())


def test_to_pose_sequence_maps_coco_body_points():
    seq = make_sequence()
    pose = seq.to_pose_sequence()
    np.testing.assert_array_equal(pose.joint(Joint.RIGHT_WRIST), seq.keypoints[:, 10])
    np.testing.assert_array_equal(pose.joint(Joint.LEFT_ANKLE), seq.keypoints[:, 15])
    assert pose.fps == seq.fps


def test_save_and_load_round_trip(tmp_path):
    seq = make_sequence()
    path = seq.save(default_pose_path(tmp_path / "clip.mp4"))
    assert path.name == "clip.wholebody.npz"

    loaded = WholeBodySequence.load(path)

    np.testing.assert_allclose(loaded.keypoints, seq.keypoints, rtol=1e-6)
    assert loaded.frame_indices.tolist() == seq.frame_indices.tolist()
    assert (loaded.fps, loaded.width, loaded.height, loaded.model) == (5.0, 64, 48, "fake.onnx")


def test_found_needs_half_the_group():
    seq = make_sequence()
    seq.keypoints[0, list(LEFT_HAND)[:12], 2] = 0.0  # 12 of 21 hand points lost
    seq.keypoints[2, list(LEFT_HAND)[:10], 2] = 0.0  # 10 of 21 lost
    assert seq.found(LEFT_HAND).tolist() == [False, False, True, True]


def test_coverage_reports_percent_of_frames():
    result = coverage(make_sequence())
    assert result["swimmer"] == 75.0
    assert result["both hands"] == 75.0


def test_sides():
    assert side(9) == "left" and side(10) == "right" and side(0) == "center"
    assert side(RIGHT_FOOT[0]) == "right" and side(LEFT_HAND[5]) == "left"
    assert edge_side(5, 7) == "left"
    assert edge_side(5, 6) == "center"


def test_draw_skeleton_colors_left_side_blue():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    points = np.full((NUM_KEYPOINTS, 3), np.nan)
    points[5] = (0.2, 0.5, GOOD)  # left shoulder
    points[7] = (0.8, 0.5, GOOD)  # left elbow
    points[6] = (0.5, 0.9, MIN_SCORE - 1)  # right shoulder, too unsure to draw

    draw_skeleton(frame, points)

    b, g, r = frame[50, 50].astype(int)
    assert b > r and b > 150  # blue-ish (anti-aliased, so not exactly COLORS["left"])
    assert not frame[85:95, 45:55].any()


def test_render_overlay_keeps_every_frame(sample_video, tmp_path):
    seq = make_sequence(frames=5)
    out = render_overlay(sample_video, seq.frame_indices, seq.keypoints, tmp_path / "o.mp4")
    cap = cv2.VideoCapture(str(out))
    assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 10
    cap.release()
