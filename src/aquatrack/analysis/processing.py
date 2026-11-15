"""Raw pose -> processed pose: target-swimmer segments, the existing cleanup, provenance.

Order:
  1. Split the clip where the tracked box jumps to a different person, and keep only the
     segments that follow the target swimmer. Frames of anyone else are rejected before
     cleanup runs, so nothing is interpolated or smoothed across a change of swimmer.
  2. Run the existing `cleanup.clean` unchanged (score threshold, flipped frames, left/right
     swaps, impossible points, spikes, short-gap fill, light smoothing).
  3. Label every point observed / interpolated / rejected / missing.

Thresholds and their reasoning are in docs/POSE_PROCESSING.md.
"""

from dataclasses import dataclass

import numpy as np

from aquatrack.analysis.pose import cleanup
from aquatrack.analysis.pose.cleanup import DROPPED, CleanPose, Fix
from aquatrack.analysis.pose.wholebody import BODY, MIN_SCORE, WholeBodySequence
from aquatrack.contracts import (
    JointState,
    ProcessedPose,
    ProcessedPoseMeta,
    RawPose,
    RejectReason,
    Segment,
)

# A box "jumps" when it does not overlap the previous one and its centre moved farther than
# JUMP_BASE + JUMP_PER_S * seconds, in box diagonals. A stretched swimmer's box diagonal is
# about a body length and sprinters cover ~1.2 body lengths per second; the rest is slack
# for a panning camera and for boxes that change shape as an arm recovers.
JUMP_BASE = 0.5
JUMP_PER_S = 1.5


@dataclass
class Processed:
    pose: ProcessedPose
    clean: CleanPose  # the same data in the shape `cycles` and `technique` expect


def frame_boxes(raw: RawPose) -> np.ndarray:
    """(frames, 4) target box per frame in pixels, NaN where there is none.

    Legacy files have no boxes; the extent of the confidently placed body points stands in.
    """
    if raw.has_boxes:
        return raw.boxes
    boxes = np.full((len(raw), 4), np.nan)
    body = raw.keypoints[:, list(BODY)]
    for i, points in enumerate(body):
        with np.errstate(invalid="ignore"):
            good = points[points[:, 2] >= MIN_SCORE]
        if len(good) >= 4:
            boxes[i] = (
                good[:, 0].min() * raw.meta.width,
                good[:, 1].min() * raw.meta.height,
                good[:, 0].max() * raw.meta.width,
                good[:, 1].max() * raw.meta.height,
            )
    return boxes


def _consistent(a: np.ndarray, b: np.ndarray, seconds: float) -> bool:
    """Could box `b` be the same person as box `a`, `seconds` later?"""
    ix = min(a[2], b[2]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[1], b[1])
    if ix > 0 and iy > 0:
        return True
    diagonal = (np.hypot(a[2] - a[0], a[3] - a[1]) + np.hypot(b[2] - b[0], b[3] - b[1])) / 2
    moved = np.hypot((a[0] + a[2] - b[0] - b[2]) / 2, (a[1] + a[3] - b[1] - b[3]) / 2)
    return bool(moved <= (JUMP_BASE + JUMP_PER_S * seconds) * diagonal)


def find_segments(raw: RawPose) -> list[Segment]:
    """Runs of frames that follow one person, with the target swimmer's runs accepted.

    The target is the person followed for the most frames. Another run is accepted only if
    its first box is consistent with the last accepted box before it (or, going backwards,
    its last box with the first accepted box after it), so a brief switch to someone else
    is dropped without losing the swimmer on either side of it.
    """
    boxes = frame_boxes(raw)
    present = np.nonzero(np.isfinite(boxes).all(axis=1))[0]
    if len(present) == 0:
        return []
    t = raw.timestamps_s
    runs, start = [], present[0]
    for a, b in zip(present[:-1], present[1:], strict=True):
        if not _consistent(boxes[a], boxes[b], float(t[b] - t[a])):
            runs.append((int(start), int(a)))
            start = b
    runs.append((int(start), int(present[-1])))

    def frames_in(run: tuple[int, int]) -> int:
        return int(((present >= run[0]) & (present <= run[1])).sum())

    main = int(np.argmax([frames_in(r) for r in runs]))
    accepted = {main}
    last = runs[main]
    for k in range(main + 1, len(runs)):
        if _consistent(boxes[last[1]], boxes[runs[k][0]], float(t[runs[k][0]] - t[last[1]])):
            accepted.add(k)
            last = runs[k]
    first = runs[main]
    for k in range(main - 1, -1, -1):
        if _consistent(boxes[runs[k][1]], boxes[first[0]], float(t[first[0]] - t[runs[k][1]])):
            accepted.add(k)
            first = runs[k]
    return [Segment(start=r[0], end=r[1], accepted=k in accepted) for k, r in enumerate(runs)]


def process(raw: RawPose) -> Processed:
    segments = find_segments(raw)
    other = np.zeros(len(raw), dtype=bool)
    for s in segments:
        if not s.accepted:
            other[s.start : s.end + 1] = True
    raw_present = np.isfinite(raw.keypoints[..., 0])

    keypoints = raw.keypoints.copy()
    keypoints[other] = np.nan
    clean = cleanup.clean(
        WholeBodySequence(
            keypoints=keypoints,
            fps=raw.meta.fps,
            frame_indices=raw.frame_indices,
            width=raw.meta.width,
            height=raw.meta.height,
            model=raw.meta.pose.name,
        )
    )

    flags = clean.flags.astype(np.uint16)
    has_xy = np.isfinite(clean.xy[..., 0])
    state = np.full(flags.shape, int(JointState.MISSING), dtype=np.uint8)
    state[has_xy] = int(JointState.OBSERVED)
    state[has_xy & ((flags & Fix.FILLED) > 0)] = int(JointState.INTERPOLATED)
    state[~has_xy & ((flags & int(DROPPED)) > 0)] = int(JointState.REJECTED)
    # The other person's points are rejected. Where the gap they leave is short, cleanup may
    # have filled it from the target swimmer's own frames on either side: that stays
    # INTERPOLATED, and the reason flag records that the model's point was someone else's.
    wrong_person = other[:, None] & raw_present
    state[wrong_person & ~has_xy] = int(JointState.REJECTED)
    reasons = flags.copy()
    reasons[wrong_person] |= int(RejectReason.OTHER_SWIMMER)

    pose = ProcessedPose(
        meta=ProcessedPoseMeta(
            video_sha256=raw.meta.video.sha256 if raw.meta.video else None,
            raw_schema_version=raw.meta.schema_version,
            fps=raw.meta.fps,
            width=raw.meta.width,
            height=raw.meta.height,
            flipped=bool(clean.flipped),
            segments=segments,
            processing={
                "min_score": MIN_SCORE,
                "max_gap_s": cleanup.MAX_GAP_S,
                "filled_confidence": cleanup.FILLED_CONFIDENCE,
                "smooth_sigma_s": cleanup.SMOOTH_SIGMA_S,
                "jump_base": JUMP_BASE,
                "jump_per_s": JUMP_PER_S,
            },
        ),
        frame_indices=raw.frame_indices,
        timestamps_s=raw.timestamps_s,
        xy=clean.xy,
        confidence=np.where(has_xy, clean.confidence, 0.0),
        state=state,
        reasons=reasons,
        trunk=clean.trunk,
    )
    return Processed(pose=pose, clean=clean)
