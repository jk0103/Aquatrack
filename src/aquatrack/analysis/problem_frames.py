"""Still frames from the swimmer's own video that show the feedback's priorities.

Only priorities from a stored Feedback document are shown, and only at the moments that
priority's own evidence names (its samples: one per stroke cycle). Nothing here finds a
problem: when the feedback has no priority, or no evidence moment has a frame that can be
trusted, the result is empty and says why.

A frame is trusted when, for the arm the evidence was measured on:
  - that arm is the one nearer the camera (the far arm is hidden behind the body);
  - the frame is SUPPORTED for it (usability.ArmFrame: the model's own shoulder, elbow and
    wrist inside an underwater pull that was followed, with believable segment lengths);
  - shoulder, elbow and wrist are OBSERVED (not filled in) with confidence at least
    MIN_JOINT_CONFIDENCE, and inside the picture (EDGE margin);
  - it is not much blurrier than the other candidate frames (sharpness, when measured).

Arrows point at a body point the model placed in that same frame. Selection is a pure
function (`select_frames`); `extract` reads the chosen frames from the video file.
Rules: docs/PROBLEM_FRAMES.md.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from aquatrack.contracts import (
    AnalysisResult,
    Feedback,
    FeedbackItem,
    FrameArrow,
    JointState,
    MetricSample,
    ProblemFrame,
    ProblemFrames,
    RawPose,
)

MAX_FRAMES = 5
MAX_SHIFT = 2  # frames either side of the evidence moment that may stand in for it
MIN_JOINT_CONFIDENCE = 0.5
EDGE = 0.02  # joints this close to the picture's edge (share of width/height) are cut off
BLUR_SHARE = 0.5  # sharper than this share of the median candidate, or left out
MAX_WIDTH = 1280  # stored images are scaled down to this width
JPEG_QUALITY = 85
MAX_LABEL_WORDS = 6

JOINTS = {
    "left": {"shoulder": 5, "elbow": 7, "wrist": 9},
    "right": {"shoulder": 6, "elbow": 8, "wrist": 10},
}


@dataclass
class PoseView:
    """What frame selection needs from the pose, per analysed frame. `xy` is 0-1 of the
    original (unmirrored) picture."""

    timestamps_s: np.ndarray  # (n,)
    frame_indices: np.ndarray  # (n,) video frame numbers
    xy: np.ndarray  # (n, 133, 2)
    confidence: np.ndarray  # (n, 133)
    observed: np.ndarray  # (n, 133) bool: the model's own point, kept
    supported: dict[str, np.ndarray] = field(default_factory=dict)  # arm -> (n,) bool
    camera_arm: str | None = None  # the arm nearer the camera
    timing_arm: str | None = None  # the arm the cycles were timed on
    width: int = 0
    height: int = 0


def pose_view(raw: RawPose, result: AnalysisResult) -> PoseView:
    """Re-run the (model-free) cleanup steps on the stored raw pose to know, frame by frame,
    which arm points the analysis itself trusted."""
    from aquatrack.analysis import biomechanics
    from aquatrack.analysis.metrics.cycles import analyze_strokes
    from aquatrack.analysis.processing import process
    from aquatrack.analysis.usability import arm_use

    processed = process(raw)
    clean, pose = processed.clean, processed.pose
    strokes = analyze_strokes(clean)
    use = arm_use(clean, strokes)
    side = result.coverage.camera_side if result.coverage else None
    points = clean.image_points()
    return PoseView(
        timestamps_s=np.asarray(pose.timestamps_s, dtype=float),
        frame_indices=np.asarray(pose.frame_indices),
        xy=points[..., :2],
        confidence=np.asarray(pose.confidence, dtype=float),
        observed=pose.state == JointState.OBSERVED,
        supported={arm: u.followed for arm, u in use.items()},
        camera_arm=side.arm if side else None,
        timing_arm=biomechanics.timing_arm(strokes, side) if side else None,
        width=clean.width,
        height=clean.height,
    )


# ---------- what each rule's evidence looks like in a frame ----------


@dataclass
class FrameRule:
    metric_key: str  # the evidence entry whose samples are the moments to show
    point: str  # the joint the arrow points at
    label: Callable[[MetricSample, float | None], str]  # (sample, clip's median) -> text


def _cycle_label(sample: MetricSample, median: float | None) -> str:
    if median is None or round(sample.value, 2) == round(median, 2):
        return f"This cycle took {sample.value:.2f} s"
    word = "Longer" if sample.value > median else "Shorter"
    return f"{word} cycle: {sample.value:.2f} s (usual {median:.2f})"


# Only rules whose evidence names moments in the video. A rule missing here has no frames.
FRAME_RULES: dict[str, FrameRule] = {
    # Cycles run mid-pull to mid-pull of the timing arm, so each odd cycle starts with that
    # hand under the shoulder, in the middle of its underwater pull.
    "timing.uneven_rhythm": FrameRule("cycle_duration", "wrist", _cycle_label),
}


def _median(result: AnalysisResult, key: str) -> float | None:
    m = next((m for m in result.metrics if m.key == key), None)
    return m.value if m is not None else None


def _cycle_index(result: AnalysisResult, key: str, sample: MetricSample) -> int:
    m = next((m for m in result.metrics if m.key == key), None)
    for k, s in enumerate(m.samples if m else []):
        if s.start_s == sample.start_s and s.end_s == sample.end_s:
            return k + 1
    return 0


# ---------- trust ----------


def _trusted(view: PoseView, i: int, arm: str) -> float | None:
    """The lowest joint confidence when frame `i` can be trusted for `arm`, else None."""
    if arm != view.camera_arm or not view.supported.get(arm, np.zeros(0, bool))[i : i + 1].any():
        return None
    joints = list(JOINTS[arm].values())
    if not view.observed[i, joints].all():
        return None
    conf = float(np.min(view.confidence[i, joints]))
    if conf < MIN_JOINT_CONFIDENCE:
        return None
    xy = view.xy[i, joints]
    if not np.isfinite(xy).all() or (xy < EDGE).any() or (xy > 1 - EDGE).any():
        return None
    return conf


def _nearest(view: PoseView, t_s: float) -> int:
    return int(np.argmin(np.abs(view.timestamps_s - t_s)))


def _candidates(view: PoseView, sample: MetricSample, arm: str) -> list[tuple[int, float]]:
    """Trusted frames for one evidence moment: the moment itself first, then up to MAX_SHIFT
    frames either side, never outside the sample's cycle."""
    i0 = _nearest(view, sample.t_s)
    lo = sample.start_s if sample.start_s is not None else -np.inf
    hi = sample.end_s if sample.end_s is not None else np.inf
    out = []
    for d in (0, 1, -1, 2, -2)[: 2 * MAX_SHIFT + 1]:
        i = i0 + d
        if not 0 <= i < len(view.timestamps_s):
            continue
        if not lo - 1e-6 <= view.timestamps_s[i] <= hi + 1e-6:
            continue
        conf = _trusted(view, i, arm)
        if conf is not None:
            out.append((i, conf))
    return out


# ---------- arrows ----------


def _arrow(view: PoseView, i: int, arm: str, joint: str, label: str) -> FrameArrow:
    x, y = (float(v) for v in view.xy[i, JOINTS[arm][joint]])
    # The label sits above the point when there is room, else below; kept off the edges.
    dy = -0.2 if y > 0.32 else 0.2
    lx = min(max(x + (-0.08 if x > 0.5 else 0.08), 0.14), 0.86)
    words = label.split()
    return FrameArrow(
        joint=f"{arm} {joint}",
        to=(round(x, 4), round(y, 4)),
        label_at=(round(lx, 4), round(min(max(y + dy, 0.08), 0.92), 4)),
        label=" ".join(words[:MAX_LABEL_WORDS]),
    )


# ---------- selection ----------


def _priorities(feedback: Feedback) -> list[FeedbackItem]:
    items = [i for i in feedback.items if i.category == "priority"]
    return sorted(items, key=lambda i: i.rank if i.rank is not None else 99)


def _rule_id(item: FeedbackItem) -> str:
    # Priority items are "fb.priority.<finding id>"; finding ids are "issue.<rule id>".
    return item.finding_id.removeprefix("issue.") if item.finding_id else ""


def select_frames(
    feedback: Feedback,
    result: AnalysisResult,
    view: PoseView,
    sharpness: Callable[[int], float | None] | None = None,
    max_frames: int = MAX_FRAMES,
) -> ProblemFrames:
    """At most `max_frames` frames for the feedback's priorities, main priority first, one
    per stroke cycle, the cycles furthest from the swimmer's own usual value first."""
    out = ProblemFrames(
        video_id=feedback.video_id, analysis_id=feedback.analysis_id, feedback_id=""
    )
    priorities = _priorities(feedback)
    if not priorities:
        out.empty_reason = "no_issue"
        return out

    # Per priority: its evidence moments, each with its trusted frames, best first.
    queues: list[list[tuple[FeedbackItem, MetricSample, FrameRule, list[tuple[int, float]]]]] = []
    any_rule = False
    for item in priorities:
        rule = FRAME_RULES.get(_rule_id(item))
        arm = view.timing_arm
        if rule is None or arm is None:
            continue
        any_rule = True
        median = _median(result, rule.metric_key)
        samples = [s for e in item.evidence if e.metric_key == rule.metric_key for s in e.samples]
        samples.sort(key=lambda s: -abs(s.value - median) if median is not None else 0)
        queue = []
        for s in samples:
            found = _candidates(view, s, arm)
            if found:
                queue.append((item, s, rule, found))
        queues.append(queue)
    if not any_rule:
        out.empty_reason = "no_frame_rule"
        return out

    # Leave out blurry frames: much less sharp than the other candidates of this clip.
    if sharpness is not None:
        scores: dict[int, float | None] = {}
        for queue in queues:
            for _, _, _, found in queue:
                for i, _ in found:
                    scores.setdefault(i, sharpness(i))
        known = [v for v in scores.values() if v is not None]
        floor = BLUR_SHARE * float(np.median(known)) if known else 0.0
        for queue in queues:
            for entry in queue:
                entry[3][:] = [(i, c) for i, c in entry[3] if (scores[i] or 0.0) >= floor]
        queues = [[e for e in q if e[3]] for q in queues]
    else:
        scores = {}

    # Round-robin over the priorities, main one first; one frame per cycle.
    chosen: list[ProblemFrame] = []
    cycles: set[tuple[float | None, float | None]] = set()
    while len(chosen) < max_frames and any(queues):
        for queue in queues:
            while queue:
                item, s, rule, found = queue.pop(0)
                if (s.start_s, s.end_s) in cycles:
                    continue
                cycles.add((s.start_s, s.end_s))
                i, conf = found[0]
                arm = view.timing_arm or ""
                chosen.append(
                    ProblemFrame(
                        item_id=item.id,
                        finding_id=item.finding_id,
                        rank=item.rank,
                        t_s=round(float(view.timestamps_s[i]), 3),
                        frame_index=int(view.frame_indices[i]),
                        cycle_index=_cycle_index(result, rule.metric_key, s),
                        cycle_start_s=s.start_s,
                        cycle_end_s=s.end_s,
                        width=view.width,
                        height=view.height,
                        arrows=[
                            _arrow(
                                view,
                                i,
                                arm,
                                rule.point,
                                rule.label(s, _median(result, rule.metric_key)),
                            )
                        ],
                        joint_confidence=round(conf, 3),
                        sharpness=round(scores[i], 1) if scores.get(i) is not None else None,
                    )
                )
                break
            if len(chosen) >= max_frames:
                break
    chosen.sort(key=lambda f: (f.rank if f.rank is not None else 99, f.t_s))
    out.frames = chosen
    if not chosen:
        out.empty_reason = "no_trusted_frame"
    return out


# ---------- reading frames from the video ----------


class FrameReader:
    """Reads frames by number, once each. Sharpness is measured around the arm's joints."""

    def __init__(self, video_path: str | Path, view: PoseView):
        import cv2

        self._cv2 = cv2
        self._cap = cv2.VideoCapture(str(video_path))
        if not self._cap.isOpened():
            raise ValueError("The video could not be opened.")
        self._view = view
        self._cache: dict[int, np.ndarray | None] = {}

    def close(self) -> None:
        self._cap.release()

    def frame(self, frame_index: int) -> np.ndarray | None:
        if frame_index not in self._cache:
            self._cap.set(self._cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, img = self._cap.read()
            self._cache[frame_index] = img if ok else None
        return self._cache[frame_index]

    def sharpness(self, i: int) -> float | None:
        """Variance of the Laplacian in a box around the timing arm's joints in analysed
        frame `i`; None when the frame can't be read."""
        view = self._view
        img = self.frame(int(view.frame_indices[i]))
        arm = view.timing_arm
        if img is None or arm is None:
            return None
        h, w = img.shape[:2]
        pts = view.xy[i, list(JOINTS[arm].values())] * [w, h]
        pad = 0.08 * max(w, h)
        x0, y0 = (np.nanmin(pts, axis=0) - pad).astype(int)
        x1, y1 = (np.nanmax(pts, axis=0) + pad).astype(int)
        crop = img[max(y0, 0) : min(y1, h), max(x0, 0) : min(x1, w)]
        if crop.size == 0:
            return None
        gray = self._cv2.cvtColor(crop, self._cv2.COLOR_BGR2GRAY)
        return float(self._cv2.Laplacian(gray, self._cv2.CV_64F).var())

    def jpeg(self, frame_index: int) -> tuple[bytes, int, int] | None:
        img = self.frame(frame_index)
        if img is None:
            return None
        h, w = img.shape[:2]
        if w > MAX_WIDTH:
            img = self._cv2.resize(img, (MAX_WIDTH, round(h * MAX_WIDTH / w)))
            h, w = img.shape[:2]
        ok, buf = self._cv2.imencode(".jpg", img, [self._cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        return (buf.tobytes(), w, h) if ok else None


def extract(
    feedback: Feedback,
    result: AnalysisResult,
    raw: RawPose,
    video_path: str | Path,
    out_dir: Path,
) -> tuple[ProblemFrames, dict[str, Path]]:
    """Choose the frames and write them as JPEGs into `out_dir`. Returns the document and
    {file name: path}. A frame that can't be read is left out."""
    view = pose_view(raw, result)
    reader = FrameReader(video_path, view)
    try:
        chosen = select_frames(feedback, result, view, sharpness=reader.sharpness)
        files: dict[str, Path] = {}
        kept = []
        for n, f in enumerate(chosen.frames, start=1):
            encoded = reader.jpeg(f.frame_index)
            if encoded is None:
                continue
            data, w, h = encoded
            name = f"{n}.jpg"
            path = out_dir / name
            path.write_bytes(data)
            files[name] = path
            kept.append(f.model_copy(update={"image": name, "width": w, "height": h}))
        chosen.frames = kept
        if not kept and not chosen.empty_reason:
            chosen.empty_reason = "no_trusted_frame"
        return chosen, files
    finally:
        reader.close()
