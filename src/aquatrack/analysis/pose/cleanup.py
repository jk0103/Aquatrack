"""Clean a raw whole-body sequence into points later steps can trust.

Steps, in order:
  1. Drop points the model scored below `MIN_SCORE`.
  2. Orient the clip so the swimmer's head points right (mirror x if needed, and remember it).
  3. Drop whole frames whose body line points the wrong way (head and feet swapped, the
     stock model's usual streamline mistake) or whose trunk length is far off.
  4. Swap left/right limbs back when that keeps them consistent with earlier frames, and
     drop a limb the model drew on top of the other one.
  5. Drop impossible points: legs on the head's side of the hips, ankles at the wrists,
     limbs much longer than usual, hands far from their wrist, feet far from their ankle.
  6. Drop one-frame spikes.
  7. Fill short gaps by interpolation; leave long gaps missing.
  8. Smooth jitter with a short local line fit, weighting each point by its confidence.

Distances are in trunk lengths (shoulder midpoint to hip midpoint), so thresholds and later
measures don't depend on zoom. Every point gets a 0-1 confidence and flags saying what
cleanup did to it.
"""

import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from enum import IntFlag
from pathlib import Path

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from aquatrack.analysis.pose.base import COCO_INDEX, Joint, PoseSequence
from aquatrack.analysis.pose.wholebody import (
    LEFT_FOOT,
    LEFT_HAND,
    MIN_SCORE,
    NUM_KEYPOINTS,
    RIGHT_FOOT,
    RIGHT_HAND,
    WholeBodySequence,
)

L_SHOULDER, R_SHOULDER, L_ELBOW, R_ELBOW, L_WRIST, R_WRIST = 5, 6, 7, 8, 9, 10
L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANKLE, R_ANKLE = 11, 12, 13, 14, 15, 16

# Raw RTMW score at which confidence reaches 1. MIN_SCORE maps to ~0.3.
FULL_CONFIDENCE_SCORE = 5.5
# Confidence multipliers for points cleanup had to guess.
SWAPPED_CONFIDENCE = 0.8
FILLED_CONFIDENCE = 0.3

MAX_AXIS_TURN_DEG = 60  # body line this far off the clip's direction = flipped frame
TRUNK_RATIO_RANGE = (0.6, 1.6)  # frame trunk length vs the clip's
MAX_SEGMENT_RATIO = 1.7  # limb segment vs its clip median
KNEE_MAX_FORWARD = 0.3  # trunk lengths in front of the hips, along the body line
ANKLE_MAX_FORWARD = 0.1
ANKLE_WRIST_MIN_DIST = 0.4
HAND_MAX_FROM_WRIST = 0.5
FOOT_MAX_FROM_ANKLE = 0.5
SWAP_MAX_LOOKBACK_S = 0.5
SWAP_MIN_SEPARATION = 0.3  # left and right limbs must have been this far apart to judge a swap
MERGED_MAX_DIST = 0.15  # left and right points this close count as drawn on one spot
MERGED_WERE_APART = 0.6
SPIKE_SLACK = 0.4  # trunk lengths, on top of what the fastest hand can move
MAX_POINT_SPEED = 12.0  # trunk lengths per second; a recovering hand reaches ~10
MAX_GAP_S = 0.2
SMOOTH_SIGMA_S = 0.04
TRUNK_WINDOW_S = 1.0

ARM_CHAINS = ([L_ELBOW, L_WRIST, *LEFT_HAND], [R_ELBOW, R_WRIST, *RIGHT_HAND])
LEG_CHAINS = ([L_KNEE, L_ANKLE, *LEFT_FOOT], [R_KNEE, R_ANKLE, *RIGHT_FOOT])
SEGMENTS = {  # name: [(parent, child) for left, right]
    "upper arm": [(L_SHOULDER, L_ELBOW), (R_SHOULDER, R_ELBOW)],
    "forearm": [(L_ELBOW, L_WRIST), (R_ELBOW, R_WRIST)],
    "thigh": [(L_HIP, L_KNEE), (R_HIP, R_KNEE)],
    "shin": [(L_KNEE, L_ANKLE), (R_KNEE, R_ANKLE)],
}


class Fix(IntFlag):
    """What cleanup did to a point. Combined per point in `CleanPose.flags`."""

    LOW_SCORE = 1  # dropped: model unsure
    BAD_FRAME = 2  # dropped: whole frame flipped or wrong size
    IMPOSSIBLE = 4  # dropped: anatomically impossible
    SPIKE = 8  # dropped: one-frame jump
    SWAPPED = 16  # left/right swapped back
    FILLED = 32  # interpolated over a short gap


DROPPED = Fix.LOW_SCORE | Fix.BAD_FRAME | Fix.IMPOSSIBLE | Fix.SPIKE


@dataclass
class CleanPose:
    """Cleaned whole-body points, oriented so the swimmer's head is on the right.

    `xy` is (frames, 133, 2) in pixels of the oriented frame (x mirrored when `flipped`),
    NaN where missing. `confidence` is 0-1 per point (0 when missing; low when filled or
    guessed). `trunk` is the shoulder-to-hip length per frame in pixels, smoothed over ~1 s.
    """

    xy: np.ndarray
    confidence: np.ndarray
    flags: np.ndarray
    trunk: np.ndarray
    fps: float
    frame_indices: np.ndarray
    width: int
    height: int
    flipped: bool
    model: str = ""

    def __len__(self) -> int:
        return len(self.xy)

    def hip_center(self) -> np.ndarray:
        return (self.xy[:, L_HIP] + self.xy[:, R_HIP]) / 2

    def shoulder_center(self) -> np.ndarray:
        return (self.xy[:, L_SHOULDER] + self.xy[:, R_SHOULDER]) / 2

    def body_axis(self) -> np.ndarray:
        """(frames, 2) unit vector from hip midpoint to shoulder midpoint."""
        axis = self.shoulder_center() - self.hip_center()
        return axis / np.linalg.norm(axis, axis=1, keepdims=True)

    def body_units(self) -> np.ndarray:
        """(frames, 133, 2) points relative to the hip midpoint, in trunk lengths.

        Head toward +x, y pointing down as in the image.
        """
        return (self.xy - self.hip_center()[:, None]) / self.trunk[:, None, None]

    def image_points(self) -> np.ndarray:
        """(frames, 133, 3): x, y normalized to the original (unmirrored) frame, and confidence."""
        x = self.xy[..., 0]
        if self.flipped:
            x = self.width - x
        return np.stack([x / self.width, self.xy[..., 1] / self.height, self.confidence], axis=-1)

    def to_pose_sequence(self) -> PoseSequence:
        """The 13 `Joint` body points (normalized oriented frame, 0-1 confidence)."""
        keypoints = np.full((len(self), len(Joint), 3), np.nan)
        for joint, coco_index in COCO_INDEX.items():
            keypoints[:, joint, 0] = self.xy[:, coco_index, 0] / self.width
            keypoints[:, joint, 1] = self.xy[:, coco_index, 1] / self.height
            keypoints[:, joint, 2] = self.confidence[:, coco_index]
        return PoseSequence(keypoints=keypoints, fps=self.fps)

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        np.savez_compressed(
            path,
            xy=self.xy.astype(np.float32),
            confidence=self.confidence.astype(np.float32),
            flags=self.flags,
            trunk=self.trunk.astype(np.float32),
            fps=self.fps,
            frame_indices=self.frame_indices,
            width=self.width,
            height=self.height,
            flipped=self.flipped,
            model=self.model,
        )
        return path

    @classmethod
    def load(cls, path: str | Path) -> "CleanPose":
        with np.load(path) as d:
            return cls(
                xy=d["xy"].astype(np.float64),
                confidence=d["confidence"].astype(np.float64),
                flags=d["flags"],
                trunk=d["trunk"].astype(np.float64),
                fps=float(d["fps"]),
                frame_indices=d["frame_indices"],
                width=int(d["width"]),
                height=int(d["height"]),
                flipped=bool(d["flipped"]),
                model=str(d["model"]),
            )


def default_clean_path(video_path: str | Path) -> Path:
    video_path = Path(video_path)
    return video_path.with_name(f"{video_path.stem}.clean.npz")


def _nanmean2(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Midpoint of two (frames, 2) tracks, or whichever one exists."""
    with np.errstate(invalid="ignore"), _quiet():
        return np.nanmean(np.stack([a, b]), axis=0)


@contextmanager
def _quiet():
    """Silence numpy's all-NaN warnings, which are expected for missing points."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        yield


def _rolling_nanmedian(values: np.ndarray, window: int) -> np.ndarray:
    half = window // 2
    padded = np.pad(values, (half, half), constant_values=np.nan)
    with _quiet():
        return np.nanmedian(sliding_window_view(padded, 2 * half + 1), axis=-1)


def _trunk_and_axis(xy: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    shoulders = _nanmean2(xy[:, L_SHOULDER], xy[:, R_SHOULDER])
    hips = _nanmean2(xy[:, L_HIP], xy[:, R_HIP])
    axis = shoulders - hips
    trunk = np.linalg.norm(axis, axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        unit = axis / trunk[:, None]
    return trunk, unit, hips


class _Cleaner:
    def __init__(self, seq: WholeBodySequence):
        self.seq = seq
        self.n = len(seq)
        self.xy = seq.keypoints[..., :2] * (seq.width, seq.height)
        self.score = seq.keypoints[..., 2].copy()
        self.flags = np.zeros((self.n, NUM_KEYPOINTS), dtype=np.uint8)
        self.flipped = False
        self.ref_trunk = np.full(self.n, np.nan)

    def drop(self, frames, points, why: Fix) -> None:
        present = ~np.isnan(self.xy[frames, points, 0])
        self.flags[frames, points] |= np.where(present, why, 0).astype(np.uint8)
        self.xy[frames, points] = np.nan
        self.score[frames, points] = np.nan

    def run(self) -> CleanPose:
        with np.errstate(invalid="ignore"):
            low = ~(self.score >= MIN_SCORE)
        self.drop(*np.nonzero(low & ~np.isnan(self.xy[..., 0])), Fix.LOW_SCORE)
        self.orient()
        self.drop_bad_frames()
        self.fix_swaps()
        self.drop_impossible()
        self.drop_spikes()
        confidence = np.clip(self.score / FULL_CONFIDENCE_SCORE, 0, 1)
        confidence = np.where(np.isnan(confidence), 0.0, confidence)
        confidence[(self.flags & Fix.SWAPPED) > 0] *= SWAPPED_CONFIDENCE
        confidence = self.fill_gaps(confidence)
        xy = self.smooth(confidence)
        trunk, _, _ = _trunk_and_axis(xy)
        trunk = _rolling_nanmedian(trunk, max(1, round(TRUNK_WINDOW_S * self.seq.fps)))
        return CleanPose(
            xy=xy,
            confidence=confidence,
            flags=self.flags,
            trunk=trunk,
            fps=self.seq.fps,
            frame_indices=self.seq.frame_indices,
            width=self.seq.width,
            height=self.seq.height,
            flipped=self.flipped,
            model=self.seq.model,
        )

    def orient(self) -> None:
        _, unit, _ = _trunk_and_axis(self.xy)
        with _quiet():
            head_x = np.nanmedian(unit[:, 0])
        if head_x < 0:
            self.xy[..., 0] = self.seq.width - self.xy[..., 0]
            self.flipped = True

    def drop_bad_frames(self) -> None:
        trunk, unit, _ = _trunk_and_axis(self.xy)
        with _quiet():
            direction = np.nanmedian(unit, axis=0)
        direction /= np.linalg.norm(direction)
        with np.errstate(invalid="ignore"):
            turned = unit @ direction < np.cos(np.radians(MAX_AXIS_TURN_DEG))
        trunk = np.where(turned, np.nan, trunk)
        window = max(1, round(TRUNK_WINDOW_S * self.seq.fps))
        ref = _rolling_nanmedian(trunk, window)
        with _quiet():
            ref = np.where(np.isnan(ref), np.nanmedian(trunk), ref)
        with np.errstate(invalid="ignore"):
            ratio = trunk / ref
            bad = turned | (ratio < TRUNK_RATIO_RANGE[0]) | (ratio > TRUNK_RATIO_RANGE[1])
        for f in np.nonzero(bad)[0]:
            self.drop(f, slice(None), Fix.BAD_FRAME)
        self.ref_trunk = ref

    def fix_swaps(self) -> None:
        lookback = max(1, round(SWAP_MAX_LOOKBACK_S * self.seq.fps))
        for left, right in (ARM_CHAINS, LEG_CHAINS):
            keys = (left[:2], right[:2])  # elbow + wrist, or knee + ankle
            last: dict[int, tuple[int, np.ndarray]] = {}
            for f in range(self.n):
                t = self.ref_trunk[f]
                prev = {p: xy for p, (pf, xy) in last.items() if f - pf <= lookback}
                straight, crossed, apart = 0.0, 0.0, 0.0
                usable = True
                for lk, rk in zip(*keys, strict=True):
                    cur_l, cur_r = self.xy[f, lk], self.xy[f, rk]
                    if np.isnan(cur_l).any() or np.isnan(cur_r).any():
                        usable = False
                        break
                    if lk not in prev or rk not in prev:
                        usable = False
                        break
                    straight += np.linalg.norm(cur_l - prev[lk]) + np.linalg.norm(cur_r - prev[rk])
                    crossed += np.linalg.norm(cur_l - prev[rk]) + np.linalg.norm(cur_r - prev[lk])
                    apart += np.linalg.norm(prev[lk] - prev[rk])
                # When both limbs were in the same place (arms together in streamline, legs
                # overlapping side-on) the labels can't be told apart, so leave them.
                if (
                    usable
                    and apart / t > SWAP_MIN_SEPARATION * len(keys[0])
                    and crossed < 0.5 * straight
                    and (straight - crossed) / t > 0.3
                ):
                    self.xy[f, left + right] = self.xy[f, right + left]
                    self.score[f, left + right] = self.score[f, right + left]
                    self.flags[f, left + right] = self.flags[f, right + left]
                    present = ~np.isnan(self.xy[f, left + right, 0])
                    self.flags[f, np.array(left + right)[present]] |= int(Fix.SWAPPED)
                self._drop_merged(f, left, right, prev, t)
                for p in keys[0] + keys[1]:
                    if not np.isnan(self.xy[f, p]).any():
                        last[p] = (f, self.xy[f, p].copy())

    def _drop_merged(self, f: int, left: list[int], right: list[int], prev: dict, t: float):
        """Both sides' point on one spot, though they were apart just before: the model drew
        one limb twice (usually the hidden one onto the visible one). Drop the one that
        jumped, and for a wrist or ankle the hand or foot after it too."""
        for i in range(2):
            lk, rk = left[i], right[i]
            if lk not in prev or rk not in prev:
                continue
            cur_l, cur_r = self.xy[f, lk], self.xy[f, rk]
            together = np.linalg.norm(cur_l - cur_r) / t < MERGED_MAX_DIST
            were_apart = np.linalg.norm(prev[lk] - prev[rk]) / t > MERGED_WERE_APART
            if together and were_apart:
                jumped_left = np.linalg.norm(cur_l - prev[lk]) > np.linalg.norm(cur_r - prev[rk])
                chain = left if jumped_left else right
                self.drop(f, chain[i:] if i == 1 else chain[i], Fix.IMPOSSIBLE)

    def drop_impossible(self) -> None:
        trunk = self.ref_trunk[:, None]
        _, unit, hips = _trunk_and_axis(self.xy)
        with np.errstate(invalid="ignore"):

            def forward(p):
                return np.einsum("fd,fd->f", self.xy[:, p] - hips, unit) / trunk[:, 0]

            def dist(a, b):
                return np.linalg.norm(self.xy[:, a] - self.xy[:, b], axis=-1) / trunk[:, 0]

            # Legs on the head's side of the hips.
            for knee, ankle, foot in ((L_KNEE, L_ANKLE, LEFT_FOOT), (R_KNEE, R_ANKLE, RIGHT_FOOT)):
                bad_knee = forward(knee) > KNEE_MAX_FORWARD
                bad_ankle = forward(ankle) > ANKLE_MAX_FORWARD
                bad_ankle |= (dist(ankle, L_WRIST) < ANKLE_WRIST_MIN_DIST) | (
                    dist(ankle, R_WRIST) < ANKLE_WRIST_MIN_DIST
                )
                self.drop(np.nonzero(bad_knee)[0], knee, Fix.IMPOSSIBLE)
                for f in np.nonzero(bad_ankle)[0]:
                    self.drop(f, [ankle, *foot], Fix.IMPOSSIBLE)
                for p in foot:
                    far = np.linalg.norm(self.xy[:, p] - self.xy[:, ankle], axis=-1) / trunk[:, 0]
                    self.drop(np.nonzero(far > FOOT_MAX_FROM_ANKLE)[0], p, Fix.IMPOSSIBLE)

            # Limb segments much longer than this clip's usual (pooled over both sides).
            for pairs in SEGMENTS.values():
                lengths = np.stack([dist(a, b) for a, b in pairs], axis=1)
                with _quiet():
                    usual = np.nanmedian(lengths)
                for i, (_, child) in enumerate(pairs):
                    too_long = lengths[:, i] > MAX_SEGMENT_RATIO * usual
                    self.drop(np.nonzero(too_long)[0], child, Fix.IMPOSSIBLE)

            # Hands: the hand model's wrist must agree with the body wrist, and fingers must
            # stay near the hand. When they disagree we can't tell which is right: drop both.
            for wrist, hand in ((L_WRIST, LEFT_HAND), (R_WRIST, RIGHT_HAND)):
                disagree = dist(wrist, hand[0]) > HAND_MAX_FROM_WRIST
                for f in np.nonzero(disagree)[0]:
                    self.drop(f, [wrist, *hand], Fix.IMPOSSIBLE)
                with _quiet():
                    center = np.nanmedian(self.xy[:, list(hand)], axis=1)
                for p in hand:
                    far = np.linalg.norm(self.xy[:, p] - center, axis=-1) / trunk[:, 0]
                    self.drop(np.nonzero(far > HAND_MAX_FROM_WRIST)[0], p, Fix.IMPOSSIBLE)

    def drop_spikes(self) -> None:
        """Drop points far from the median of the two samples on each side."""
        half = 2
        padded = np.pad(self.xy, ((half, half), (0, 0), (0, 0)), constant_values=np.nan)
        windows = sliding_window_view(padded, 2 * half + 1, axis=0)  # (F, 133, 2, 5)
        with _quiet():
            median = np.nanmedian(windows, axis=-1)
        enough = (~np.isnan(windows[:, :, 0, :])).sum(axis=-1) >= 3
        allowed = SPIKE_SLACK + MAX_POINT_SPEED * half / self.seq.fps
        with np.errstate(invalid="ignore"):
            off = np.linalg.norm(self.xy - median, axis=-1) / self.ref_trunk[:, None]
            spikes = enough & (off > allowed)
        self.drop(*np.nonzero(spikes), Fix.SPIKE)

    def fill_gaps(self, confidence: np.ndarray) -> np.ndarray:
        max_gap = max(1, round(MAX_GAP_S * self.seq.fps))
        for p in range(NUM_KEYPOINTS):
            present = ~np.isnan(self.xy[:, p, 0])
            idx = np.nonzero(present)[0]
            for a, b in zip(idx[:-1], idx[1:], strict=True):
                gap = b - a - 1
                if 0 < gap <= max_gap:
                    t = (np.arange(a + 1, b) - a) / (b - a)
                    self.xy[a + 1 : b, p] = self.xy[a, p] + t[:, None] * (
                        self.xy[b, p] - self.xy[a, p]
                    )
                    confidence[a + 1 : b, p] = FILLED_CONFIDENCE * min(
                        confidence[a, p], confidence[b, p]
                    )
                    self.flags[a + 1 : b, p] |= int(Fix.FILLED)
        return confidence

    def smooth(self, confidence: np.ndarray) -> np.ndarray:
        """Confidence-weighted local linear fit over a short Gaussian window.

        A line rather than a plain average, so a moving hand isn't dragged toward where it
        was (or will be) at the clip's ends and around gaps. Missing points stay missing.
        """
        sigma = SMOOTH_SIGMA_S * self.seq.fps
        if sigma < 0.5:
            return self.xy.copy()
        half = int(np.ceil(3 * sigma))
        offsets = np.arange(-half, half + 1, dtype=float)
        kernel = np.exp(-0.5 * (offsets / sigma) ** 2)
        present = ~np.isnan(self.xy[..., 0])
        weight = np.where(present, np.maximum(confidence, 1e-3), 0.0)
        values = np.where(present[..., None], self.xy, 0.0)
        pad = ((half, half), (0, 0))
        w = sliding_window_view(np.pad(weight, pad), 2 * half + 1, axis=0) * kernel
        v = sliding_window_view(np.pad(values, (*pad, (0, 0))), 2 * half + 1, axis=0)
        s0, s1, s2 = w.sum(-1), (w * offsets).sum(-1), (w * offsets**2).sum(-1)
        t0 = (v * w[:, :, None]).sum(-1)
        t1 = (v * (w * offsets)[:, :, None]).sum(-1)
        det = s0 * s2 - s1**2
        with np.errstate(invalid="ignore", divide="ignore"):
            linear = (s2[..., None] * t0 - s1[..., None] * t1) / det[..., None]
            average = t0 / s0[..., None]
        # Fall back to the weighted average when the window can't fit a line (one sample).
        well_posed = (det > 1e-6 * np.maximum(s0, 1e-12) ** 2)[..., None]
        smoothed = np.where(well_posed, linear, average)
        return np.where(present[..., None], smoothed, np.nan)


def clean(seq: WholeBodySequence) -> CleanPose:
    """Clean a raw whole-body sequence. See the module docstring for the steps."""
    return _Cleaner(seq).run()
