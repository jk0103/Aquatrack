"""Draw the whole-body skeleton (body, feet, hands; no face) and event labels on the video."""

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from aquatrack.analysis.pose.wholebody import MIN_SCORE, SKELETON, edge_side, side
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


@dataclass(frozen=True)
class OverlayEvent:
    """A label shown for a moment from `frame` (a source video frame), with an optional
    ring around one keypoint, e.g. the wrist at the start of a stroke cycle."""

    frame: int
    text: str
    side: str = "center"
    point: int | None = None


def _draw_events(frame: np.ndarray, events: list[OverlayEvent], points: np.ndarray | None):
    height, width = frame.shape[:2]
    scale = max(0.5, min(width, height) / 720)
    for row, event in enumerate(events):
        color = COLORS[event.side]
        origin = (int(20 * scale), int((40 + 36 * row) * scale))
        cv2.putText(frame, event.text, origin, 0, scale, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(frame, event.text, origin, 0, scale, color, 2, cv2.LINE_AA)
        if event.point is not None and points is not None and not np.isnan(points[event.point, 0]):
            center = (int(points[event.point, 0] * width), int(points[event.point, 1] * height))
            cv2.circle(frame, center, int(18 * scale), color, 2, cv2.LINE_AA)


def render_overlay(
    video_path: str | Path,
    frame_indices: np.ndarray,
    points: np.ndarray,
    out_path: str | Path,
    min_value: float = MIN_SCORE,
    events: list[OverlayEvent] = (),
    event_seconds: float = 0.6,
) -> Path:
    """Write the source video with the skeleton drawn on every frame.

    `points` is (frames, 133, 3): x, y normalized to the source frame, then a score or
    confidence; points below `min_value` are not drawn. `frame_indices` says which source
    frame each row belongs to. With a frame step, frames between two analyzed ones show
    the last analyzed pose.
    """
    out_path = Path(out_path)
    info = read_video_info(video_path)
    hold = max(1, round(event_seconds * info.fps))
    writer = _open_writer(out_path, info.fps, (info.width, info.height))
    try:
        current = -1
        for index, frame in iter_frames(video_path):
            while current + 1 < len(points) and frame_indices[current + 1] <= index:
                current += 1
            pose = points[current] if current >= 0 else None
            if pose is not None:
                draw_skeleton(frame, pose, min_value)
            active = [e for e in events if e.frame <= index < e.frame + hold]
            if active:
                _draw_events(frame, active, pose)
            writer.write(frame)
    finally:
        writer.release()
    return out_path


def default_overlay_path(video_path: str | Path) -> Path:
    video_path = Path(video_path)
    return video_path.with_name(f"{video_path.stem}.overlay.mp4")
