"""Key-frame images: each technique measure drawn on the frame it was read from, so the
number can be checked by eye. For every measure type the frame whose value is closest to
the clip's median is used."""

from pathlib import Path

import cv2
import numpy as np

from aquatrack.analysis.metrics.technique import ARMS, LEGS, NOSE, TechniqueReport, Value
from aquatrack.analysis.pose.cleanup import CleanPose
from aquatrack.analysis.pose.overlay import COLORS

REFERENCE = (60, 230, 255)  # yellow (BGR): travel line and other references
WHITE = (255, 255, 255)
MAX_WIDTH = 1600


def default_keyframes_dir(video_path: str | Path) -> Path:
    video_path = Path(video_path)
    return video_path.with_name(f"{video_path.stem}.measures")


class _Canvas:
    """Draws oriented-frame points (head to the right) onto the original video frame."""

    def __init__(self, frame: np.ndarray, pose: CleanPose, k: int, horizon: float):
        self.img = frame
        self.pose = pose
        self.k = k
        self.unit = max(1, round(min(frame.shape[:2]) / 360))
        travel = np.array([np.cos(horizon), np.sin(horizon)])
        self.travel, self.down = travel, np.array([-travel[1], travel[0]])

    def p(self, xy: np.ndarray) -> tuple[int, int]:
        x = self.pose.width - xy[0] if self.pose.flipped else xy[0]
        return int(round(x)), int(round(xy[1]))

    def pt(self, index: int) -> np.ndarray:
        return self.pose.xy[self.k, index]

    def line(self, a, b, color, thickness: int = 2) -> None:
        cv2.line(
            self.img, self.p(a), self.p(b), (0, 0, 0), (thickness + 2) * self.unit, cv2.LINE_AA
        )
        cv2.line(self.img, self.p(a), self.p(b), color, thickness * self.unit, cv2.LINE_AA)

    def dot(self, a, color) -> None:
        cv2.circle(self.img, self.p(a), 4 * self.unit, color, -1, cv2.LINE_AA)

    def text(self, a, label: str, color=WHITE, scale: float = 0.6) -> None:
        x, y = self.p(a)
        org = (x + 6 * self.unit, y - 6 * self.unit)
        s = scale * self.unit / 2
        cv2.putText(self.img, label, org, 0, s, (0, 0, 0), 4 * self.unit, cv2.LINE_AA)
        cv2.putText(self.img, label, org, 0, s, color, max(1, self.unit), cv2.LINE_AA)

    def travel_line(self, through, length: float) -> None:
        self.line(through - self.travel * length, through + self.travel * length, REFERENCE, 1)

    def title(self, label: str) -> None:
        s = 0.7 * self.unit / 2
        org = (10 * self.unit, 20 * self.unit)
        cv2.putText(self.img, label, org, 0, s, (0, 0, 0), 4 * self.unit, cv2.LINE_AA)
        cv2.putText(self.img, label, org, 0, s, WHITE, max(1, self.unit), cv2.LINE_AA)


def _nearest_median(values: list[Value]) -> Value | None:
    framed = [v for v in values if v.frame is not None]
    if not framed:
        return None
    median = np.median([v.value for v in framed])
    return min(framed, key=lambda v: abs(v.value - median))


def _arm(c: _Canvas, arm: str):
    s, e, w, _ = ARMS[arm]
    color = COLORS[arm]
    c.line(c.pt(s), c.pt(e), color)
    c.line(c.pt(e), c.pt(w), color)
    return c.pt(s), c.pt(e), c.pt(w), color


def _draw_catch(c: _Canvas, v: Value, report: TechniqueReport) -> str:
    s, e, w, color = _arm(c, v.side)
    trunk = c.pose.trunk[c.k]
    c.line(e, e + c.down * 0.6 * trunk, REFERENCE, 1)  # straight down from the elbow
    c.travel_line(s, 0.8 * trunk)
    c.text(e, f"forearm {v.value:.0f} deg from vertical")
    above = report.measures["catch_elbow_above_wrist"].values
    match = next((x for x in above if x.frame == v.frame), None)
    if match:
        c.text(w, f"elbow {match.value:+.2f} trunk above wrist")
    return f"Catch ({v.side} arm): forearm angle and elbow height"


def _draw_elbow(c: _Canvas, v: Value, report: TechniqueReport) -> str:
    _, e, _, color = _arm(c, v.side)
    c.dot(e, color)
    c.text(e, f"elbow {v.value:.0f} deg")
    return f"Smallest elbow angle in the pull ({v.side} arm)"


def _draw_pull_depth(c: _Canvas, v: Value, report: TechniqueReport) -> str:
    s, _, w, color = _arm(c, v.side)
    trunk = c.pose.trunk[c.k]
    c.travel_line(s, 1.0 * trunk)
    foot = s + c.travel * ((w - s) @ c.travel)
    c.line(foot, w, REFERENCE, 1)
    c.text(w, f"{v.value:.2f} trunk below shoulder")
    return f"Deepest point of the pull ({v.side} arm)"


def _draw_entry(c: _Canvas, v: Value, report: TechniqueReport) -> str:
    s, _, w, color = _arm(c, v.side)
    trunk = c.pose.trunk[c.k]
    for point, name in ((s, "shoulder"), (c.pt(NOSE), "nose")):
        c.line(point - c.down * 0.5 * trunk, point + c.down * 0.5 * trunk, REFERENCE, 1)
        c.text(point - c.down * 0.5 * trunk, name, REFERENCE, 0.5)
    c.dot(w, color)
    c.text(w, f"{v.value:.2f} trunk ahead of shoulder")
    return f"Hand first seen after recovery ({v.side} arm)"


def _draw_body(c: _Canvas, v: Value, report: TechniqueReport) -> str:
    xy = c.pose.xy[c.k]
    shoulders, hips = (xy[5] + xy[6]) / 2, (xy[11] + xy[12]) / 2
    ankles = (xy[15] + xy[16]) / 2
    for point in (shoulders, hips, ankles):
        c.dot(point, WHITE)
    c.line(shoulders, ankles, WHITE)
    c.travel_line(hips, 1.6 * c.pose.trunk[c.k])
    c.text(shoulders, f"body line {v.value:.1f} deg", WHITE)
    depth = next(
        (
            x
            for x in report.measures["hip_depth_below_shoulders"].values
            if x.cycle_start == v.cycle_start
        ),
        None,
    )
    if depth:
        c.text(hips, f"hips {depth.value:.2f} trunk below shoulders", WHITE)
    return "Body line against the travel direction (yellow)"


def _draw_head(c: _Canvas, v: Value, report: TechniqueReport) -> str:
    xy = c.pose.xy[c.k]
    ear = xy[3] if c.pose.confidence[c.k, 3] >= c.pose.confidence[c.k, 4] else xy[4]
    nose = xy[NOSE]
    shoulders, hips = (xy[5] + xy[6]) / 2, (xy[11] + xy[12]) / 2
    c.line(hips, shoulders + (shoulders - hips) * 0.3, REFERENCE, 1)
    c.line(ear, nose + (nose - ear), WHITE)
    c.dot(ear, WHITE)
    c.dot(nose, WHITE)
    c.text(nose, f"head lift {v.value:.0f} deg", WHITE)
    return "Head: ear-to-nose line against the body line (yellow)"


def _draw_legs(c: _Canvas, v: Value, report: TechniqueReport, what: str) -> str:
    for side, (hip, knee, ankle, foot) in LEGS.items():
        color = COLORS[side]
        c.line(c.pt(hip), c.pt(knee), color)
        c.line(c.pt(knee), c.pt(ankle), color)
        if what == "foot":
            c.line(c.pt(foot[2]), c.pt(foot[0]), REFERENCE)  # heel to big toe
    hip, knee, ankle, _ = LEGS["left"]
    if what == "knee":
        c.text(c.pt(knee), f"knee bend up to {v.value:.0f} deg", WHITE)
        return "Largest knee bend in the cycle"
    ankle = LEGS[v.side][2] if v.side else ankle
    c.text(c.pt(ankle), f"{v.side or ''} foot {v.value:.0f} deg off the shin line", WHITE)
    return "Foot point: heel-to-toe line (yellow) against the shin"


DRAWINGS = {
    "catch": ("catch_forearm_from_vertical", _draw_catch),
    "elbow_min": ("elbow_min_pull", _draw_elbow),
    "pull_depth": ("pull_depth", _draw_pull_depth),
    "entry": ("entry_ahead_of_shoulder", _draw_entry),
    "body_line": ("body_line_angle", _draw_body),
    "head": ("head_angle", _draw_head),
    "knee": ("knee_bend_max", lambda c, v, r: _draw_legs(c, v, r, "knee")),
    "foot": ("foot_point", lambda c, v, r: _draw_legs(c, v, r, "foot")),
}


def render_keyframes(
    video_path: str | Path,
    pose: CleanPose,
    report: TechniqueReport,
    horizon: np.ndarray,
    out_dir: str | Path,
) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video_path))
    written = []
    try:
        for name, (measure, draw) in DRAWINGS.items():
            m = report.measures[measure]
            preferred = [x for x in m.values if m.prefer_side and x.side == m.prefer_side]
            v = _nearest_median(preferred or m.values)
            if v is None:
                continue
            source = int(pose.frame_indices[v.frame])
            cap.set(cv2.CAP_PROP_POS_FRAMES, source)
            ok, frame = cap.read()
            if not ok:
                continue
            canvas = _Canvas(frame, pose, v.frame, horizon[v.frame])
            title = draw(canvas, v, report)
            canvas.title(f"{title} - frame {source}")
            img = canvas.img
            if img.shape[1] > MAX_WIDTH:
                scale = MAX_WIDTH / img.shape[1]
                img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            path = out_dir / f"{name}.jpg"
            cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
            written.append(path)
    finally:
        cap.release()
    return written
