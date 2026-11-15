"""Which arm points a measurement may use, and which arm faces the camera.

A pose model's score says how sure the model is, not whether the joint was visible. On
underwater side clips RTMW keeps drawing an arm, with high scores, while the real arm is
above the water (recovery) or behind the body (far arm). Four things are kept apart here:

  1. model score          -> cleanup (MIN_SCORE) and the OBSERVED/INTERPOLATED/... states
  2. observability        -> `followed`: the frame lies inside an underwater pull that was
                             seen passing straight down (reach -> exit, see `cycles`)
  3. temporal consistency -> the pull detector only accepts an arm that moves the way an arm
                             can (front, then down, then back, at a possible speed)
  4. metric usability     -> each metric states which of these it needs (`biomechanics`)

Points outside a followed pull are not deleted: the raw and processed pose keep both arms.
They are only not used for arm geometry, and they are reported as "not verified".
"""

import warnings
from dataclasses import dataclass
from enum import IntEnum

import numpy as np

from aquatrack.analysis.metrics.cycles import (
    ARMS,
    FRONT_MAX,
    StrokeAnalysis,
    arm_angle,
    main_stretch,
    pull_angle,
)
from aquatrack.analysis.pose import cleanup
from aquatrack.analysis.pose.cleanup import DROPPED, CleanPose, Fix
from aquatrack.contracts import ArmObservation, CameraSide, SessionInfo

ELBOW = {"left": 7, "right": 8}
FULL_PULL_DEG = 150  # a pull followed at least this far back counts as followed to the push
# Evidence for the camera side, each compared between the two arms.
MIN_EXIT_GAP_DEG = 10  # median angle the pulls were followed to
MIN_SCORE_GAP = 0.5  # median raw model score of shoulder, elbow and wrist
MIN_SIDE_VIEW_AXIS = 0.7  # |cos| of the body line against the picture's horizontal
FACE_UP_STROKES = {"backstroke"}
MIN_SEGMENT_SHARE = 0.5  # of the arm's own median upper-arm / forearm length in its pulls
MIN_FRAMES_FOR_USUAL = 10  # pull frames needed before "usual length" means anything
MIN_SIZE_SHARE = 0.75  # trunk size against its largest in the clip; cos^2(30 degrees)


@dataclass
class ArmUse:
    """Per frame, what is known about one arm's elbow and wrist. `kind` holds exactly one
    class per frame (see `ArmFrame`), so shares of the classes always add up to 100%."""

    arm: str
    kind: np.ndarray  # (frames,) uint8 of ArmFrame
    in_front: np.ndarray  # (frames,) bool: MODEL_ONLY frames where the arm is drawn ahead
    collapsed: np.ndarray  # (frames,) bool: inside a pull, but a segment is impossibly short
    pulls: int
    pulls_followed_back: int

    @property
    def followed(self) -> np.ndarray:
        return self.kind == ArmFrame.SUPPORTED


class ArmFrame(IntEnum):
    """One class per frame and arm, checked in this order.

    SUPPORTED     model points for shoulder, elbow and wrist inside an underwater pull that
                  was seen passing straight down, with believable segment lengths. The only
                  class arm metrics read. "Supported" by the movement, not seen by a person.
    INTERPOLATED  the elbow or wrist was filled across a short gap (never measured).
    MODEL_ONLY    the model placed elbow and wrist, but nothing backs it up: the arm is
                  outside a followed pull (recovery in the air, behind the body, or drawn
                  stretched in front), or inside one with a collapsed segment.
    REJECTED      the model's point was thrown out by cleanup and not filled.
    MISSING       no point at all.
    """

    SUPPORTED = 0
    INTERPOLATED = 1
    MODEL_ONLY = 2
    REJECTED = 3
    MISSING = 4


def arm_segments(pose: CleanPose, arm: str) -> tuple[np.ndarray, np.ndarray]:
    """Upper-arm and forearm length per frame, in trunk lengths, as drawn in the picture."""
    shoulder, wrist = ARMS[arm]
    elbow = ELBOW[arm]
    with np.errstate(invalid="ignore"):
        upper = np.linalg.norm(pose.xy[:, elbow] - pose.xy[:, shoulder], axis=1) / pose.trunk
        fore = np.linalg.norm(pose.xy[:, wrist] - pose.xy[:, elbow], axis=1) / pose.trunk
    return upper, fore


def arm_use(pose: CleanPose, strokes: StrokeAnalysis) -> dict[str, ArmUse]:
    out = {}
    filled = (pose.flags & Fix.FILLED) > 0
    dropped = (pose.flags & int(DROPPED)) > 0
    for arm, (_, wrist) in ARMS.items():
        elbow = ELBOW[arm]
        angle, reliable = arm_angle(pose, arm)
        angle = pull_angle(np.where(reliable > 0, angle, np.nan))
        in_pull = np.zeros(len(pose), dtype=bool)
        pulls = strokes.pulls.get(arm, [])
        for p in pulls:
            in_pull[p.start : p.exit + 1] = True
        has = np.isfinite(pose.xy[:, [elbow, wrist], 0])
        interpolated = (has & filled[:, [elbow, wrist]]).any(axis=1)
        model = has.all(axis=1) & ~interpolated  # both points are the model's own
        candidate = in_pull & model & (reliable > 0)

        # A segment far shorter than this arm's own usual length in its pulls. A real arm
        # does get shorter in the picture when it points toward or away from the camera, so
        # only a collapse below MIN_SEGMENT_SHARE (the arm pointing more than 60 degrees
        # out of the picture) is ruled out. Typical case: the hand leaves the water at the
        # end of the push and the model pulls the wrist up against the elbow.
        collapsed = np.zeros(len(pose), dtype=bool)
        if candidate.sum() >= MIN_FRAMES_FOR_USUAL:
            for length in arm_segments(pose, arm):
                usual = float(np.median(length[candidate]))
                with np.errstate(invalid="ignore"):
                    collapsed |= candidate & (length < MIN_SEGMENT_SHARE * usual)

        kind = np.full(len(pose), int(ArmFrame.MISSING), dtype=np.uint8)
        kind[dropped[:, [elbow, wrist]].any(axis=1) & ~has.all(axis=1)] = ArmFrame.REJECTED
        kind[model] = ArmFrame.MODEL_ONLY
        kind[interpolated] = ArmFrame.INTERPOLATED
        kind[candidate & ~collapsed] = ArmFrame.SUPPORTED
        with np.errstate(invalid="ignore"):
            in_front = (kind == ArmFrame.MODEL_ONLY) & (np.abs(angle) <= FRONT_MAX)
        out[arm] = ArmUse(
            arm=arm,
            kind=kind,
            in_front=in_front,
            collapsed=collapsed,
            pulls=len(pulls),
            pulls_followed_back=sum(p.exit_angle_deg >= FULL_PULL_DEG for p in pulls),
        )
    return out


def unusable_points(pose: CleanPose, use: dict[str, ArmUse]) -> np.ndarray:
    """(frames, 133) bool: arm points metrics must not read. In a frame that is not
    SUPPORTED the elbow and wrist (and hand) of that arm are ruled out; the points stay in
    the pose data."""
    out = np.zeros(pose.xy.shape[:2], dtype=bool)
    chains = {"left": cleanup.ARM_CHAINS[0], "right": cleanup.ARM_CHAINS[1]}
    for arm, u in use.items():
        out[np.ix_(~u.followed, chains[arm])] = True
    return out


@dataclass
class ViewCheck:
    """Whether the swimmer stays at a steady distance and angle to the camera."""

    size_ratio: dict[int, float]  # cycle start frame -> apparent size / largest in the clip
    unsuitable: set[int]  # cycle start frames seen too much at an angle
    status: str  # "steady", "changing" or "unknown"
    note: str = ""


def view_check(pose: CleanPose, cycles: list) -> ViewCheck:
    """Flag stroke cycles filmed too far off side-on, from the swimmer's apparent size.

    What can be said from one camera: when a swimmer passes a camera that stays in place,
    the trunk looks largest when they are exactly side-on and shrinks with the square of the
    cosine of the angle off side-on (further away, and turned). So a cycle where the trunk is
    under MIN_SIZE_SHARE (0.75) of its largest size in the clip is roughly 30 degrees or
    more off side-on, and picture angles and lengths there are distorted.

    What cannot: the angle itself. If the camera is never side-on, or zooms, or moves with
    the swimmer at a fixed slant, this sees nothing, so "steady" is not proof of a side view.
    """
    sizes = {}
    for c in cycles:
        trunk = pose.trunk[c.start : c.end + 1]
        if np.isfinite(trunk).any():
            sizes[c.start] = float(np.nanmedian(trunk))
    if len(sizes) < 2:
        return ViewCheck({}, set(), "unknown", "Too few stroke cycles to tell.")
    largest = max(sizes.values())
    ratio = {k: v / largest for k, v in sizes.items()}
    unsuitable = {k for k, r in ratio.items() if r < MIN_SIZE_SHARE}
    if not unsuitable:
        return ViewCheck(ratio, unsuitable, "steady")
    return ViewCheck(
        ratio,
        unsuitable,
        "changing",
        f"The swimmer's size in the picture changes a lot through the clip (down to "
        f"{min(ratio.values()):.0%} of its largest): the camera sees part of the swim at an "
        f"angle. {len(unsuitable)} of {len(sizes)} stroke cycles are left out of position "
        "and angle measurements.",
    )


def camera_side(
    pose: CleanPose, raw_keypoints: np.ndarray, strokes: StrokeAnalysis, session: SessionInfo
) -> CameraSide:
    """The arm nearer the camera, only when the swim direction and the footage agree.

    Geometry: a face-down swimmer heading to the right of the picture shows the camera their
    right side (their left side when heading left); face-up strokes are the other way round.
    That assumes the video is not mirrored and the model's left/right labels are right, so
    it has to be backed by the footage: the near arm is followed further back through the
    pull, and usually scores higher. Any disagreement means "not established".
    """
    camera = session.camera.lower()
    if camera and not camera.startswith("underwater"):
        return CameraSide(reason=f"Only worked out for underwater side views, not {camera}.")
    axis = pose.body_axis()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        level = float(np.nanmedian(np.abs(axis[:, 0])))
    if not np.isfinite(level) or level < MIN_SIDE_VIEW_AXIS:
        return CameraSide(reason="The swimmer is not seen from the side.")

    face_up = session.stroke.lower() in FACE_UP_STROKES
    heading_left = bool(pose.flipped)
    by_direction = "left" if heading_left != face_up else "right"
    other = "right" if by_direction == "left" else "left"
    evidence = [
        f"Swimming toward the {'left' if heading_left else 'right'} of the picture, "
        f"face {'up' if face_up else 'down'}: the {by_direction} side faces the camera."
    ]

    votes = []
    exits = {
        arm: [p.exit_angle_deg for p in strokes.pulls.get(arm, [])] for arm in (by_direction, other)
    }
    if exits[by_direction] and exits[other]:
        gap = float(np.median(exits[by_direction]) - np.median(exits[other]))
        if abs(gap) >= MIN_EXIT_GAP_DEG:
            votes.append(gap > 0)
            evidence.append(
                f"The {by_direction if gap > 0 else other} arm's pulls are followed further "
                f"back ({abs(gap):.0f} degrees more)."
            )
    scores = {}
    for arm, (shoulder, wrist) in ARMS.items():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            scores[arm] = float(np.nanmedian(raw_keypoints[:, [shoulder, ELBOW[arm], wrist], 2]))
    if all(np.isfinite(v) for v in scores.values()):
        gap = scores[by_direction] - scores[other]
        if abs(gap) >= MIN_SCORE_GAP:
            votes.append(gap > 0)
            evidence.append(
                f"The model is more confident about the {by_direction if gap > 0 else other} arm."
            )
    if not votes:
        return CameraSide(
            evidence=evidence,
            reason="The footage does not show clearly which arm is nearer the camera.",
        )
    if not all(votes):
        return CameraSide(
            evidence=evidence,
            reason="The swim direction and the footage disagree about which arm is nearer.",
        )
    return CameraSide(arm=by_direction, evidence=evidence)


def arm_observations(
    pose: CleanPose, use: dict[str, ArmUse], side: CameraSide
) -> list[ArmObservation]:
    stretch = main_stretch(pose)
    if stretch is None:
        return []
    span = slice(stretch[0], stretch[1] + 1)

    def pct(mask: np.ndarray) -> float:
        return round(100.0 * float(mask[span].mean()), 1)

    out = []
    for arm, u in use.items():
        share = {k: pct(u.kind == k) for k in ArmFrame}
        # Rounding must not make the five classes add up to anything but 100.
        share[ArmFrame.MISSING] = round(
            100.0 - sum(v for k, v in share.items() if k is not ArmFrame.MISSING), 1
        )
        out.append(
            ArmObservation(
                arm=arm,
                camera_side=side.arm == arm,
                pulls=u.pulls,
                pulls_followed_back=u.pulls_followed_back,
                supported_pct=share[ArmFrame.SUPPORTED],
                interpolated_pct=share[ArmFrame.INTERPOLATED],
                model_only_pct=share[ArmFrame.MODEL_ONLY],
                model_only_in_front_pct=pct(u.in_front),
                model_only_collapsed_pct=pct(u.collapsed),
                rejected_pct=share[ArmFrame.REJECTED],
                missing_pct=max(0.0, share[ArmFrame.MISSING]),
                # Schema 1.1 names, kept so older readers still get sensible numbers.
                followed_pct=share[ArmFrame.SUPPORTED],
                in_front_pct=pct(u.in_front),
                unverified_pct=round(share[ArmFrame.MODEL_ONLY] - pct(u.in_front), 1),
                not_observed_pct=round(
                    share[ArmFrame.INTERPOLATED]
                    + share[ArmFrame.REJECTED]
                    + max(0.0, share[ArmFrame.MISSING]),
                    1,
                ),
            )
        )
    return out
