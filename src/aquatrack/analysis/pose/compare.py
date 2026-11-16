"""Compare two pose runs of the same video: a new one against a reference.

Used by the real-inference acceptance test (scripts/gpu_acceptance.py) to compare what a GPU
worker produced with the pose data saved in Phase 1. Two runs of the same models are not
expected to be identical: a different ONNX export, onnxruntime version, CPU against GPU
arithmetic, or a detector box that differs by a pixel all move the points a little. So this
reports how far apart the runs are and lets the caller judge against stated tolerances; it
never hides a difference and never calls two runs "equal".
"""
# ruff: noqa: E501  (report sentences are kept whole)

from dataclasses import asdict, dataclass, field

import numpy as np

from aquatrack.contracts import RawPose

BODY_JOINTS = list(range(5, 17))  # shoulders, elbows, wrists, hips, knees, ankles
MIN_SCORE = 3.0  # the cleanup cut-off: points under it are not used downstream


@dataclass
class Tolerances:
    """What the acceptance test treats as "the same models, behaving the same way". These
    are engineering choices for a first run, to be revisited once one real run exists."""

    frames_exact: bool = True  # the same frames must have been decoded
    detected_frames_pct: float = 2.0  # frames with a swimmer box, difference in points
    box_iou_median: float = 0.90
    body_px_median: float = 3.0  # median distance of confident body joints, in pixels
    body_px_p95: float = 12.0
    score_median_abs: float = 0.5  # raw RTMW scores are on a 0 to about 10 scale
    confident_agreement_pct: float = 95.0  # same side of the 3.0 cut-off


@dataclass
class PoseComparison:
    comparable: bool = True
    reasons: list[str] = field(default_factory=list)  # why not comparable
    frames_new: int = 0
    frames_reference: int = 0
    detected_pct_new: float = 0.0
    detected_pct_reference: float = 0.0
    box_iou_median: float | None = None
    body_px_median: float | None = None
    body_px_p95: float | None = None
    body_px_max: float | None = None
    score_median_new: float | None = None
    score_median_reference: float | None = None
    confident_agreement_pct: float | None = None
    worst_joint: str = ""
    differences: list[str] = field(default_factory=list)  # outside tolerance
    context: list[str] = field(default_factory=list)  # known reasons for small differences
    within_tolerance: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _iou(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    x1, y1 = np.maximum(a[:, 0], b[:, 0]), np.maximum(a[:, 1], b[:, 1])
    x2, y2 = np.minimum(a[:, 2], b[:, 2]), np.minimum(a[:, 3], b[:, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area = lambda r: (r[:, 2] - r[:, 0]) * (r[:, 3] - r[:, 1])  # noqa: E731
    return inter / (area(a) + area(b) - inter)


def compare_raw_pose(
    new: RawPose, reference: RawPose, tol: Tolerances | None = None
) -> PoseComparison:
    tol = tol or Tolerances()
    out = PoseComparison(
        frames_new=len(new.frame_indices), frames_reference=len(reference.frame_indices)
    )
    a, b = new.meta, reference.meta
    if a.video.sha256 != b.video.sha256:
        out.comparable = False
        out.reasons.append("The two runs are of different video files.")
        return out
    if a.config.frame_step != b.config.frame_step:
        out.comparable = False
        out.reasons.append("The two runs sampled frames differently.")
        return out
    # Things that legitimately differ between runs, stated rather than hidden.
    if a.pose.sha256 != b.pose.sha256:
        out.context.append(
            "Different ONNX export of the pose model (exports are not bit-identical)."
        )
    if a.pose.version != b.pose.version:
        out.context.append(f"Pose runtime: '{a.pose.version}' against '{b.pose.version}'.")
    if a.detector.version != b.detector.version:
        out.context.append(
            f"Detector library: '{a.detector.version}' against '{b.detector.version}'."
        )
    if a.config != b.config:
        out.context.append("The model configuration differs between the runs.")

    same_frames = out.frames_new == out.frames_reference and np.array_equal(
        new.frame_indices, reference.frame_indices
    )
    if not same_frames:
        if tol.frames_exact:
            out.differences.append(
                f"Frames differ: {out.frames_new} in the new run, {out.frames_reference} in the reference."
            )
        common, ia, ib = np.intersect1d(
            new.frame_indices, reference.frame_indices, return_indices=True
        )
        if len(common) == 0:
            out.comparable = False
            out.reasons.append("The runs share no frames.")
            return out
    else:
        ia = ib = np.arange(out.frames_new)

    has_a = np.isfinite(new.boxes[:, 0])
    has_b = np.isfinite(reference.boxes[:, 0])
    out.detected_pct_new = round(100 * float(has_a.mean()), 2)
    out.detected_pct_reference = round(100 * float(has_b.mean()), 2)
    if abs(out.detected_pct_new - out.detected_pct_reference) > tol.detected_frames_pct:
        out.differences.append(
            f"Frames with a swimmer box: {out.detected_pct_new}% against {out.detected_pct_reference}%."
        )

    both = has_a[ia] & has_b[ib]
    if both.any():
        iou = _iou(new.boxes[ia][both], reference.boxes[ib][both])
        out.box_iou_median = round(float(np.median(iou)), 4)
        if out.box_iou_median < tol.box_iou_median:
            out.differences.append(
                f"Median box overlap {out.box_iou_median} (wanted {tol.box_iou_median})."
            )

    ka, kb = new.keypoints[ia][:, BODY_JOINTS], reference.keypoints[ib][:, BODY_JOINTS]
    scale = np.array([a.width, a.height], dtype=float)
    conf_a, conf_b = ka[..., 2] >= MIN_SCORE, kb[..., 2] >= MIN_SCORE
    seen = np.isfinite(ka[..., 2]) & np.isfinite(kb[..., 2])
    if seen.any():
        out.confident_agreement_pct = round(100 * float((conf_a == conf_b)[seen].mean()), 2)
        out.score_median_new = round(float(np.median(ka[..., 2][seen])), 3)
        out.score_median_reference = round(float(np.median(kb[..., 2][seen])), 3)
        if abs(out.score_median_new - out.score_median_reference) > tol.score_median_abs:
            out.differences.append(
                f"Median score {out.score_median_new} against {out.score_median_reference}: "
                "possibly a different model generation (their score scales differ)."
            )
        if out.confident_agreement_pct < tol.confident_agreement_pct:
            out.differences.append(
                f"Only {out.confident_agreement_pct}% of points fall on the same side of the confidence cut-off."
            )
    confident = conf_a & conf_b
    if confident.any():
        dist = np.linalg.norm((ka[..., :2] - kb[..., :2]) * scale, axis=-1)
        d = dist[confident]
        out.body_px_median = round(float(np.median(d)), 3)
        out.body_px_p95 = round(float(np.percentile(d, 95)), 3)
        out.body_px_max = round(float(d.max()), 3)
        per_joint = [
            np.median(dist[:, j][confident[:, j]]) if confident[:, j].any() else 0
            for j in range(len(BODY_JOINTS))
        ]
        names = [
            "l_shoulder",
            "r_shoulder",
            "l_elbow",
            "r_elbow",
            "l_wrist",
            "r_wrist",
            "l_hip",
            "r_hip",
            "l_knee",
            "r_knee",
            "l_ankle",
            "r_ankle",
        ]
        out.worst_joint = names[int(np.argmax(per_joint))]
        if out.body_px_median > tol.body_px_median:
            out.differences.append(
                f"Median joint distance {out.body_px_median} px (wanted {tol.body_px_median})."
            )
        if out.body_px_p95 > tol.body_px_p95:
            out.differences.append(
                f"95th percentile joint distance {out.body_px_p95} px (wanted {tol.body_px_p95})."
            )
    else:
        out.differences.append("No body joint was confident in both runs.")
    out.within_tolerance = not out.differences
    return out


def compare_metrics(new: list[dict], reference: list[dict], rel: float = 0.05) -> list[dict]:
    """Metric by metric: status and value of the two analyses. A status that changed, or a
    value more than `rel` away (relative, or absolute for values near zero), is flagged."""
    ref = {m["key"]: m for m in reference}
    rows = []
    for m in new:
        r = ref.get(m["key"])
        if r is None:
            rows.append({"key": m["key"], "flag": "only in the new run"})
            continue
        va, vb = m.get("value"), r.get("value")
        flag = ""
        if m.get("status") != r.get("status"):
            flag = f"status {r.get('status')} -> {m.get('status')}"
        elif va is not None and vb is not None:
            limit = max(abs(vb) * rel, 0.5)
            if abs(va - vb) > limit:
                flag = f"value moved by {va - vb:+.3f}"
        rows.append(
            {"key": m["key"], "new": va, "reference": vb, "status": m.get("status"), "flag": flag}
        )
    return rows
