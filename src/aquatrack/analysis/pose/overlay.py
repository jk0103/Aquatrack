"""Draw the whole-body skeleton (body, feet, hands; no face) on top of the source video."""

from pathlib import Path

import cv2
import numpy as np

from aquatrack.analysis.pose.wholebody import (
    MIN_SCORE,
    SKELETON,
    WholeBodySequence,
    edge_side,
    side,
)
from aquatrack.analysis.video import iter_frames, read_video_info

# BGR. Blue is the swimmer's left, orange their right.
COLORS = {
    "left": (235, 130, 30),
    "right": (20, 140, 255),
    "center": (235, 235, 235),
}
_DRAWN_POINTS = sorted({i for edge in SKELETON for i in edge})


def draw_skeleton(frame: np.ndarray, points: np.ndarray, min_score: float = MIN_SCORE) -> None:
    """Draw one frame's (133, 3) normalized keypoints onto `frame` in place."""
    height, width = frame.shape[:2]
    thickness = max(1, round(min(width, height) / 300))
    radius = thickness + 1
    xy = np.round(points[:, :2] * (width, height))
    with np.errstate(invalid="ignore"):
        ok = points[:, 2] >= min_score  # NaN scores compare False

    for a, b in SKELETON:
        if ok[a] and ok[b]:
            pa, pb = tuple(int(v) for v in xy[a]), tuple(int(v) for v in xy[b])
            cv2.line(frame, pa, pb, COLORS[edge_side(a, b)], thickness, cv2.LINE_AA)
    for i in _DRAWN_POINTS:
        if ok[i]:
            center = tuple(int(v) for v in xy[i])
            cv2.circle(frame, center, radius, COLORS[side(i)], -1, cv2.LINE_AA)


def _open_writer(path: Path, fps: float, size: tuple[int, int]) -> cv2.VideoWriter:
    # H.264 plays in browsers and QuickTime; fall back to MPEG-4 Part 2 if it isn't available.
    for codec in ("avc1", "mp4v"):
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*codec), fps, size)
        if writer.isOpened():
            return writer
        writer.release()
    raise RuntimeError(f"Could not open a video writer for {path}")


def render_overlay(
    video_path: str | Path,
    pose: WholeBodySequence,
    out_path: str | Path,
    min_score: float = MIN_SCORE,
) -> Path:
    """Write the source video with the skeleton drawn on every frame.

    With a frame step, frames between two analyzed ones show the last analyzed pose.
    """
    out_path = Path(out_path)
    info = read_video_info(video_path)
    writer = _open_writer(out_path, info.fps, (info.width, info.height))
    try:
        current = -1
        for index, frame in iter_frames(video_path):
            while current + 1 < len(pose) and pose.frame_indices[current + 1] <= index:
                current += 1
            if current >= 0:
                draw_skeleton(frame, pose.keypoints[current], min_score)
            writer.write(frame)
    finally:
        writer.release()
    return out_path


def default_overlay_path(video_path: str | Path) -> Path:
    video_path = Path(video_path)
    return video_path.with_name(f"{video_path.stem}.overlay.mp4")
