"""Which way is horizontal in the swimmer's oriented frame.

Technique angles are measured against the direction of travel, not the image edge, so a
tilted camera doesn't change them. Three sources, best first:
  1. the hips' path, when the camera is still and the swimmer crosses the frame;
  2. the pool's long straight lines (lane ropes, floor lines), when the camera follows
     the swimmer so the hips hardly move in the frame;
  3. the frame's own horizontal, as a last resort.
"""

from pathlib import Path

import cv2
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from aquatrack.analysis.pose.cleanup import CleanPose

MIN_HIP_SPEED = 0.5  # trunk lengths per second along a steady line to trust the hip path
MAX_LINE_TILT_DEG = 25  # pool lines steeper than this are ignored
MIN_LINE_LENGTH = 0.3  # fraction of the frame width; arms and legs are shorter
LINE_SAMPLE_S = 0.5
LINE_SMOOTH_SAMPLES = 7  # rolling median over ~3 s of samples


def line_angle(frame_bgr: np.ndarray) -> float | None:
    """Angle (radians, image coordinates, y down) of the frame's long near-horizontal
    lines, as their length-weighted median; None when there are none."""
    height, width = frame_bgr.shape[:2]
    scale = 960 / width if width > 960 else 1.0
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    if scale != 1.0:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150)
    w = gray.shape[1]
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 720, threshold=60, minLineLength=MIN_LINE_LENGTH * w, maxLineGap=0.05 * w
    )
    if lines is None:
        return None
    x1, y1, x2, y2 = lines.reshape(-1, 4).T.astype(float)  # (N, 1, 4) in OpenCV 4, (N, 4) in 5
    angles = np.arctan2(y2 - y1, x2 - x1)
    angles = (angles + np.pi / 2) % np.pi - np.pi / 2  # direction doesn't matter
    lengths = np.hypot(x2 - x1, y2 - y1)
    keep = np.abs(angles) <= np.radians(MAX_LINE_TILT_DEG)
    if not keep.any():
        return None
    angles, lengths = angles[keep], lengths[keep]
    order = np.argsort(angles)
    cumulative = np.cumsum(lengths[order])
    return float(angles[order][np.searchsorted(cumulative, cumulative[-1] / 2)])


def _hip_path_angle(pose: CleanPose, frames: np.ndarray) -> float | None:
    hip = pose.hip_center()[frames]
    ok = ~np.isnan(hip[:, 0])
    if ok.sum() < pose.fps:
        return None
    t = frames[ok] / pose.fps
    vx, _ = np.polyfit(t, hip[ok, 0], 1)
    vy, _ = np.polyfit(t, hip[ok, 1], 1)
    speed = np.hypot(vx, vy) / np.nanmedian(pose.trunk[frames])
    if speed < MIN_HIP_SPEED or vx <= 0:  # still, or moving feet-first: the camera moves
        return None
    return float(np.arctan2(vy, vx))


def horizontal(
    pose: CleanPose, frames: np.ndarray, video_path: str | Path | None = None
) -> tuple[np.ndarray, str]:
    """Per analyzed frame, the angle (radians) of the travel direction in the oriented
    frame (head to the right, so 0 means level), and which source gave it."""
    angles = np.zeros(len(pose))
    hip = _hip_path_angle(pose, frames)
    if hip is not None:
        angles[:] = hip
        return angles, "hip path"
    if video_path is not None:
        sampled = _pool_line_angles(pose, frames, video_path)
        if sampled is not None:
            return sampled, "pool lines"
    return angles, "frame horizontal"


def _pool_line_angles(pose: CleanPose, frames: np.ndarray, video_path) -> np.ndarray | None:
    every = max(1, round(LINE_SAMPLE_S * pose.fps))
    picks = frames[::every]
    cap = cv2.VideoCapture(str(video_path))
    found_at, found = [], []
    try:
        for i in picks:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(pose.frame_indices[i]))
            ok, frame = cap.read()
            angle = line_angle(frame) if ok else None
            if angle is not None:
                found_at.append(i)
                found.append(-angle if pose.flipped else angle)  # mirror like the points
    finally:
        cap.release()
    if len(found) < max(2, len(picks) // 2):
        return None
    # A handheld camera following the swimmer tilts slowly; single frames are noisy (a few
    # degrees, from perspective and the swimmer's own edges), so take a rolling median.
    half = LINE_SMOOTH_SAMPLES // 2
    padded = np.pad(np.array(found), half, mode="edge")
    smoothed = np.median(sliding_window_view(padded, 2 * half + 1), axis=1)
    return np.interp(np.arange(len(pose)), found_at, smoothed)
