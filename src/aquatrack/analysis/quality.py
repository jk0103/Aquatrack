"""Quality report for a processed pose: what was seen, what was estimated, what was lost.

The grade comes only from the measured data below, never from the kind of video. Known
limits of a filming angle or stroke are reported separately as `filming_limitations`.
"""

import numpy as np

from aquatrack.analysis.pose.wholebody import LEFT_FOOT, LEFT_HAND, RIGHT_FOOT, RIGHT_HAND
from aquatrack.contracts import (
    BoxSource,
    JointState,
    ProcessedPose,
    QualityGrade,
    QualityReport,
    RawPose,
    SessionInfo,
    TrackingQuality,
)

BODY_JOINTS = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]  # fmt: skip
LIMBS = list(range(5, 17))
TRUNK = [5, 6, 11, 12]
PARTS = {
    "head": [0, 1, 2, 3, 4],
    "trunk": TRUNK,
    "arms": [7, 8, 9, 10],
    "legs": [13, 14, 15, 16],
    "hands": [*LEFT_HAND, *RIGHT_HAND],
    "feet": [*LEFT_FOOT, *RIGHT_FOOT],
}

# A frame has a valid pose when the trunk is anchored and most limb joints are usable.
VALID_MIN_TRUNK = 3  # of 4 shoulder and hip points
VALID_MIN_LIMBS = 8  # of 12 limb joints

# Grade criteria (engineering baseline, see docs/POSE_PROCESSING.md). All must hold for GOOD.
GOOD_MIN_VALID_PCT = 80.0
GOOD_MIN_TRUNK_PCT = 80.0
GOOD_MIN_ARMS_PCT = 60.0
GOOD_MAX_OTHER_SWIMMER_PCT = 5.0
GOOD_MIN_CYCLES = 4
# Any of these makes the grade INSUFFICIENT.
INSUFFICIENT_MAX_VALID_PCT = 40.0
INSUFFICIENT_MIN_VALID_S = 2.0


def _pct(mask: np.ndarray) -> float:
    return round(100.0 * float(mask.mean()), 1) if mask.size else 0.0


def filming_limitations(session: SessionInfo) -> list[str]:
    notes = []
    camera, stroke = session.camera.lower(), session.stroke.lower()
    if camera.startswith("underwater") or camera == "":
        notes.append(
            "Side view: the arm and leg farther from the camera are often hidden behind the body."
        )
        notes.append("Body rotation cannot be measured from a side view.")
    else:
        notes.append(
            f"The {session.camera} view has not been validated yet. Above the surface, splash "
            "and the waterline often hide most of the body."
        )
    if stroke and stroke != "freestyle":
        notes.append("Stroke timing has only been checked on freestyle so far.")
    return notes


def build_quality_report(
    raw: RawPose,
    pose: ProcessedPose,
    reliable_cycles: int,
    session: SessionInfo,
    total_frames: int,
) -> QualityReport:
    n = len(pose)
    usable = np.isin(pose.state, (JointState.OBSERVED, JointState.INTERPOLATED))
    limb_state = pose.state[:, LIMBS]
    valid = (usable[:, TRUNK].sum(axis=1) >= VALID_MIN_TRUNK) & (
        usable[:, LIMBS].sum(axis=1) >= VALID_MIN_LIMBS
    )
    fps = pose.meta.fps

    longest, run = 0, 0
    for ok in valid:
        run = 0 if ok else run + 1
        longest = max(longest, run)

    other = np.zeros(n, dtype=bool)
    for s in pose.meta.segments:
        if not s.accepted:
            other[s.start : s.end + 1] = True
    recorded = raw.has_boxes
    tracking = TrackingQuality(
        recorded=recorded,
        identity_breaks=max(0, len(pose.meta.segments) - 1),
        other_swimmer_pct=_pct(other),
    )
    if recorded:
        tracking.detected_pct = _pct(raw.box_source == BoxSource.DETECTED)
        tracking.carried_pct = _pct(raw.box_source == BoxSource.CARRIED)
        tracking.no_box_pct = _pct(raw.box_source == BoxSource.NONE)
        tracking.multiple_people_pct = _pct(raw.candidates >= 2)

    valid_pct = _pct(valid)
    parts = {name: _pct(usable[:, idx]) for name, idx in PARTS.items()}
    valid_seconds = float(valid.sum()) / fps if fps else 0.0

    reasons: list[str] = []
    if valid_pct < INSUFFICIENT_MAX_VALID_PCT:
        reasons.append(
            f"Only {valid_pct:.0f}% of frames have a usable pose "
            f"(under {INSUFFICIENT_MAX_VALID_PCT:.0f}%)."
        )
    if valid_seconds < INSUFFICIENT_MIN_VALID_S:
        reasons.append(
            f"Only {valid_seconds:.1f} s of usable pose (under {INSUFFICIENT_MIN_VALID_S:.0f} s)."
        )
    if reasons:
        grade = QualityGrade.INSUFFICIENT
    else:
        checks = [
            (valid_pct >= GOOD_MIN_VALID_PCT, f"{valid_pct:.0f}% of frames have a usable pose"),
            (
                parts["trunk"] >= GOOD_MIN_TRUNK_PCT,
                f"shoulders and hips seen {parts['trunk']:.0f}%",
            ),
            (parts["arms"] >= GOOD_MIN_ARMS_PCT, f"elbows and wrists seen {parts['arms']:.0f}%"),
            (
                tracking.other_swimmer_pct <= GOOD_MAX_OTHER_SWIMMER_PCT,
                f"{tracking.other_swimmer_pct:.0f}% of frames followed someone else",
            ),
            (reliable_cycles >= GOOD_MIN_CYCLES, f"{reliable_cycles} reliable stroke cycles"),
        ]
        failed = [text for ok, text in checks if not ok]
        grade = QualityGrade.LIMITED if failed else QualityGrade.GOOD
        reasons = (
            [f"Below the bar for a good clip: {text}." for text in failed]
            if failed
            else [f"Meets every criterion: {'; '.join(text for _, text in checks)}."]
        )

    return QualityReport(
        total_frames=total_frames,
        analyzed_frames=n,
        frames_with_swimmer=int(np.isfinite(raw.keypoints[:, 0, 0]).sum()),
        valid_pose_frames=int(valid.sum()),
        valid_pose_pct=valid_pct,
        observed_pct=_pct(limb_state == JointState.OBSERVED),
        interpolated_pct=_pct(limb_state == JointState.INTERPOLATED),
        rejected_pct=_pct(limb_state == JointState.REJECTED),
        missing_pct=_pct(limb_state == JointState.MISSING),
        per_joint_coverage={name: _pct(usable[:, i]) for i, name in enumerate(BODY_JOINTS)},
        body_part_coverage=parts,
        longest_missing_s=round(longest / fps, 2) if fps else 0.0,
        tracking=tracking,
        reliable_stroke_cycles=reliable_cycles,
        grade=grade,
        grade_reasons=reasons,
        filming_limitations=filming_limitations(session),
    )
