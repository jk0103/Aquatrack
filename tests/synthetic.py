"""A synthetic freestyle swimmer with known geometry, for tests."""

import numpy as np

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


def _rotate(vectors: np.ndarray, degrees: float) -> np.ndarray:
    a = np.radians(degrees)
    rot = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    return vectors @ rot.T


def swimmer_xy(
    t: np.ndarray,
    period: float = 1.2,
    elbow_deg: float = 180.0,
    kick_hz: float = 0.0,
    kick_amp: float = 0.15,
    foot_deg: float = 0.0,
    breaths_per_cycle: float = 0.0,
    hip_drop: float = 0.0,
    tilt_deg: float = 0.0,
    travel: float = 0.0,
) -> np.ndarray:
    """(frames, 133, 2) pixels for a swimmer heading right, both arms turning once per
    `period` seconds half a turn apart, legs straight behind.

    elbow_deg: constant elbow angle (forearm turned down from the upper arm).
    kick_hz, kick_amp: each ankle bobs up and down (trunk lengths), the legs in opposition.
    foot_deg: heel-to-toe line turned this far off the shin.
    breaths_per_cycle: the head rolls (nose comes up level with the ears) this often.
    hip_drop: hips this many trunk lengths lower than the shoulders (legs follow).
    tilt_deg: the whole picture rotated, like a tilted camera. travel: forward speed in
    trunk lengths per second (a still camera).
    """
    xy = np.zeros((len(t), NUM_KEYPOINTS, 2))
    xy[:] = SHOULDER + (TRUNK * 0.5, 0)  # face points by the head
    hip = HIP + (0, hip_drop * TRUNK)
    for side, (sh, hp) in enumerate(((5, 11), (6, 12))):
        offset = (0, 3 if side else -3)
        xy[:, sh] = SHOULDER + offset
        xy[:, hp] = hip + offset
    xy[:, [1, 2]] = SHOULDER + (TRUNK * 0.4, 0)  # eyes
    xy[:, [3, 4]] = SHOULDER + (TRUNK * 0.3, 0)  # ears
    nose_depth = np.full(len(t), 0.0)
    if breaths_per_cycle:
        nose_depth[:] = 0.15
        breath_period = period / breaths_per_cycle
        turning = (t % breath_period) < 0.35
        nose_depth[turning] = 0.0
    xy[:, 0, 0] = SHOULDER[0] + 0.5 * TRUNK
    xy[:, 0, 1] = SHOULDER[1] + nose_depth * TRUNK

    for knee, ankle, foot, dy, phase in (
        (13, 15, LEFT_FOOT, -4, 0.0),
        (14, 16, RIGHT_FOOT, 4, np.pi),
    ):
        bob = kick_amp * TRUNK * np.sin(2 * np.pi * kick_hz * t + phase) if kick_hz else 0.0
        xy[:, knee] = hip + (-0.8 * TRUNK, dy)
        xy[:, ankle, 0] = hip[0] - 1.6 * TRUNK
        xy[:, ankle, 1] = hip[1] + dy + bob
        shin = xy[:, ankle] - xy[:, knee]
        shin /= np.linalg.norm(shin, axis=1, keepdims=True)
        foot_dir = _rotate(shin, foot_deg)
        heel, big_toe, small_toe = foot[2], foot[0], foot[1]
        xy[:, heel] = xy[:, ankle] - foot_dir * 0.05 * TRUNK
        xy[:, big_toe] = xy[:, ankle] + foot_dir * 0.2 * TRUNK
        xy[:, small_toe] = xy[:, ankle] + foot_dir * 0.18 * TRUNK

    for elbow, wrist, hand, phase0 in ((7, 9, LEFT_HAND, 0.0), (8, 10, RIGHT_HAND, np.pi + 0.3)):
        theta = phase0 + 2 * np.pi * t / period
        upper = np.stack([np.cos(theta), np.sin(theta)], axis=1)
        forearm = _rotate(upper, 180.0 - elbow_deg)  # turned down (y is down)
        xy[:, elbow] = SHOULDER + 0.65 * TRUNK * upper
        xy[:, wrist] = xy[:, elbow] + 0.65 * TRUNK * forearm
        for k, p in enumerate(hand):
            xy[:, p] = xy[:, wrist] + 0.25 * TRUNK * forearm * (k / 20)

    if travel:
        xy[..., 0] += travel * TRUNK * t[:, None]
    if tilt_deg:
        center = HIP
        xy = center + _rotate(xy - center, tilt_deg)
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
