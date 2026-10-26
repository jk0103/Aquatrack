import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from aquatrack.analysis.metrics.cycles import analyze_strokes
from aquatrack.analysis.pose import cli
from aquatrack.analysis.pose.cleanup import (
    L_ANKLE,
    L_ELBOW,
    L_KNEE,
    L_WRIST,
    R_ELBOW,
    R_WRIST,
    CleanPose,
    Fix,
    clean,
)
from aquatrack.analysis.pose.wholebody import (
    LEFT_FOOT,
    LEFT_HAND,
    NUM_KEYPOINTS,
    RIGHT_FOOT,
    RIGHT_HAND,
    WholeBodySequence,
)

W, H, FPS, TRUNK = 640, 400, 25.0, 100.0
HIP = np.array([300.0, 200.0])
SHOULDER = HIP + (TRUNK, 0)


def swimmer_xy(t: np.ndarray, period: float = 1.2) -> np.ndarray:
    """(frames, 133, 2) pixels for a swimmer heading right, both arms turning once per
    `period` seconds half a turn apart, legs straight behind."""
    xy = np.zeros((len(t), NUM_KEYPOINTS, 2))
    xy[:] = SHOULDER + (TRUNK * 0.5, 0)  # face points and nose by the head
    for side, (sh, hp) in enumerate(((5, 11), (6, 12))):
        offset = (0, 3 if side else -3)
        xy[:, sh] = SHOULDER + offset
        xy[:, hp] = HIP + offset
    xy[:, [1, 2, 3, 4]] = SHOULDER + (TRUNK * 0.4, 0)
    for knee, ankle, foot, dy in ((13, 15, LEFT_FOOT, -4), (14, 16, RIGHT_FOOT, 4)):
        xy[:, knee] = HIP + (-0.8 * TRUNK, dy)
        xy[:, ankle] = HIP + (-1.6 * TRUNK, dy)
        for k, p in enumerate(foot):
            xy[:, p] = xy[:, ankle] + (-10 - 5 * k, 5)
    for elbow, wrist, hand, phase0 in ((7, 9, LEFT_HAND, 0.0), (8, 10, RIGHT_HAND, np.pi + 0.3)):
        theta = phase0 + 2 * np.pi * t / period
        direction = np.stack([np.cos(theta), np.sin(theta)], axis=1)
        xy[:, elbow] = SHOULDER + 0.65 * TRUNK * direction
        xy[:, wrist] = SHOULDER + 1.3 * TRUNK * direction
        for k, p in enumerate(hand):
            xy[:, p] = xy[:, wrist] + 0.25 * TRUNK * direction * (k / 20)
    return xy


def to_sequence(xy: np.ndarray, score: float = 6.0) -> WholeBodySequence:
    keypoints = np.concatenate([xy / (W, H), np.full((*xy.shape[:2], 1), score)], axis=-1)
    return WholeBodySequence(
        keypoints=keypoints,
        fps=FPS,
        frame_indices=np.arange(len(xy)),
        width=W,
        height=H,
        model="synthetic",
    )


def times(frames: int = 150) -> np.ndarray:
    return np.arange(frames) / FPS


def test_clean_swimmer_is_left_alone():
    xy = swimmer_xy(times())
    pose = clean(to_sequence(xy))

    assert not pose.flipped
    assert not (pose.flags & (Fix.BAD_FRAME | Fix.IMPOSSIBLE | Fix.SPIKE | Fix.SWAPPED)).any()
    assert np.nanmedian(pose.trunk) == pytest.approx(TRUNK)
    assert np.all(pose.confidence[:, :23] == 1.0)
    np.testing.assert_allclose(pose.xy[:, :17], xy[:, :17], atol=3.0)
    units = pose.body_units()
    assert units[0, 15, 0] == pytest.approx(-1.6, abs=0.05)  # ankle 1.6 trunks behind hips


def test_head_on_the_left_is_mirrored_and_maps_back():
    xy = swimmer_xy(times())
    mirrored = xy.copy()
    mirrored[..., 0] = W - mirrored[..., 0]

    pose = clean(to_sequence(mirrored))

    assert pose.flipped
    np.testing.assert_allclose(pose.xy[:, :17], xy[:, :17], atol=3.0)
    # image_points undoes the mirror for drawing on the original video
    np.testing.assert_allclose(pose.image_points()[:, :17, 0] * W, mirrored[:, :17, 0], atol=3.0)


def test_left_right_swap_is_fixed():
    xy = swimmer_xy(times())
    swapped = xy.copy()
    left = [L_ELBOW, L_WRIST, *LEFT_HAND]
    right = [R_ELBOW, R_WRIST, *RIGHT_HAND]
    swapped[40, left + right] = xy[40, right + left]

    pose = clean(to_sequence(swapped))

    assert pose.flags[40, L_WRIST] & Fix.SWAPPED
    assert not pose.flags[39, L_WRIST] & Fix.SWAPPED
    np.testing.assert_allclose(pose.xy[40, L_WRIST], xy[40, L_WRIST], atol=5.0)
    assert pose.confidence[40, L_WRIST] < 1.0


def test_legs_on_arms_frame_is_dropped_then_filled():
    xy = swimmer_xy(times())
    flipped_frame = xy.copy()
    # The stock model's streamline mistake: the whole body drawn head-to-feet reversed.
    flipped_frame[60, :, 0] = 2 * HIP[0] - xy[60, :, 0]

    pose = clean(to_sequence(flipped_frame))

    assert pose.flags[60, L_ANKLE] & Fix.BAD_FRAME
    assert pose.flags[60, L_ANKLE] & Fix.FILLED  # a one-frame gap is filled
    np.testing.assert_allclose(pose.xy[60, L_ANKLE], xy[60, L_ANKLE], atol=3.0)
    assert pose.confidence[60, L_ANKLE] < 0.5


def test_ankle_at_the_wrist_and_knee_ahead_of_hips_are_dropped():
    t = times()
    xy = swimmer_xy(t)
    xy[30, L_ANKLE] = xy[30, R_WRIST]
    xy[70, L_KNEE] = HIP + (0.6 * TRUNK, 0)

    pose = clean(to_sequence(xy))

    assert pose.flags[30, L_ANKLE] & Fix.IMPOSSIBLE
    assert pose.flags[70, L_KNEE] & Fix.IMPOSSIBLE


def test_short_gap_filled_long_gap_left_missing():
    seq = to_sequence(swimmer_xy(times()))
    seq.keypoints[50:53, L_WRIST, 2] = 1.0  # below MIN_SCORE: 3 frames missing
    seq.keypoints[80:96, L_WRIST, 2] = 1.0  # 16 frames missing

    pose = clean(seq)

    assert np.all(pose.flags[50:53, L_WRIST] & Fix.FILLED)
    assert not np.isnan(pose.xy[50:53, L_WRIST]).any()
    assert np.all(pose.confidence[50:53, L_WRIST] <= 0.3)
    assert np.isnan(pose.xy[80:96, L_WRIST]).all()
    assert np.all(pose.confidence[80:96, L_WRIST] == 0)


def test_smoothing_reduces_jitter():
    xy = swimmer_xy(times())
    noisy = xy.copy()
    noisy[:, 0] += np.random.default_rng(1).normal(0, 3, size=(len(xy), 2))

    pose = clean(to_sequence(noisy))

    assert np.std(pose.xy[:, 0] - xy[:, 0]) < 0.8 * np.std(noisy[:, 0] - xy[:, 0])


def test_known_number_of_cycles_and_stroke_rate():
    pose = clean(to_sequence(swimmer_xy(times(150), period=1.2)))

    strokes = analyze_strokes(pose)

    left = [c for c in strokes.cycles if c.arm == "left"]
    right = [c for c in strokes.cycles if c.arm == "right"]
    assert len(left) == 4  # arm straight back at 0.6, 1.8, 3.0, 4.2, 5.4 s
    assert len(right) == 4  # at 1.14, 2.34, 3.54, 4.74, 5.94 s
    assert all(c.trusted for c in strokes.cycles)
    assert strokes.rate_per_min["left"] == pytest.approx(50, abs=1)
    assert strokes.stroke_rate_per_min == pytest.approx(50, abs=1)
    for c in left:
        assert c.duration_s == pytest.approx(1.2, abs=0.05)
        assert abs(c.reach - (c.start + c.end) / 2) <= 1  # hand furthest forward mid-cycle
    assert [s.name for s in strokes.sections] == ["start", "middle", "end"]
    assert {c.section for c in strokes.cycles} == {"start", "middle", "end"}


def test_cycle_with_hidden_arm_is_not_trusted():
    seq = to_sequence(swimmer_xy(times(150), period=1.2))
    seq.keypoints[50:70, L_WRIST, 2] = 1.0  # left wrist lost for most of a cycle

    strokes = analyze_strokes(clean(seq))

    left = [c for c in strokes.cycles if c.arm == "left"]
    unsure = [c for c in left if not c.trusted]
    assert len(unsure) == 1 and "reliable" in unsure[0].reason
    assert strokes.rate_per_min["left"] == pytest.approx(50, abs=1)  # from trusted ones


def test_clean_pose_save_load(tmp_path):
    pose = clean(to_sequence(swimmer_xy(times(40))))
    loaded = CleanPose.load(pose.save(tmp_path / "x.clean.npz"))
    np.testing.assert_allclose(loaded.xy, pose.xy, rtol=1e-5)
    assert loaded.flipped == pose.flipped and loaded.flags.dtype == np.uint8


def test_cli_reuse_writes_everything(tmp_path: Path):
    video = tmp_path / "swim.mp4"
    frames = 60
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    for _ in range(frames):
        writer.write(np.zeros((H, W, 3), dtype=np.uint8))
    writer.release()
    to_sequence(swimmer_xy(times(frames))).save(tmp_path / "swim.wholebody.npz")

    cli.main([str(video), "--reuse", "--overlay"])

    result = json.loads((tmp_path / "swim.cycles.json").read_text())
    assert result["stroke_rate_per_min"] == pytest.approx(50, abs=1)
    assert result["cycles"][0]["start_frame"] == result["cycles"][0]["start"]
    assert (tmp_path / "swim.clean.npz").exists()
    assert (tmp_path / "swim.overlay.mp4").exists()
