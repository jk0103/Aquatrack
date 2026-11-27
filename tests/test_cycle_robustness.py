"""Two weaknesses of the stroke-cycle timing found on synthetic swimmers (2026-11-27), and
the checks that close them. Synthetic swimmers only: these are not measured swims.

1. Arm points missing for a long stretch hid whole strokes; the cycles on either side were
   joined into one long cycle that was still trusted.
2. Cycle time was read from the wrist passing under the shoulder, so a swimmer who bent the
   elbow differently on alternate strokes looked like one with an uneven rhythm.
"""

import numpy as np
import pytest
from synthetic import FPS, swimmer_xy, times, to_sequence

from aquatrack.analysis.metrics.cycles import MAX_UNSEEN_SHARE, analyze_strokes
from aquatrack.analysis.pose.cleanup import L_ELBOW, L_WRIST, R_ELBOW, R_WRIST, clean

PERIOD = 1.2
ARM_POINTS = [L_ELBOW, R_ELBOW, L_WRIST, R_WRIST]


def strokes(xy, hide=None):
    seq = to_sequence(xy)
    for start, stop, points in hide or []:
        seq.keypoints[start:stop, points, 2] = 0.4  # far below what the cleaner accepts
    return analyze_strokes(clean(seq))


def alternating_elbow(t):
    bent, straight = swimmer_xy(t, PERIOD, elbow_deg=95.0), swimmer_xy(t, PERIOD, elbow_deg=160.0)
    odd = (np.floor(t / PERIOD).astype(int) % 2).astype(bool)
    xy = bent.copy()
    xy[odd] = straight[odd]
    return xy


def test_strokes_hidden_by_missing_arm_points_do_not_make_a_trusted_long_cycle():
    t = times(360)
    hide = [(s, s + 55, ARM_POINTS) for s in range(30, 360, 90)]  # 2.2 s gaps: 1.8 cycles each
    found = strokes(swimmer_xy(t, PERIOD, elbow_deg=120.0), hide)
    assert found.cycles, "the strokes seen between the gaps are still found"
    long_ones = [c for c in found.cycles if c.duration_s > 1.5 * PERIOD]
    assert long_ones and not any(c.trusted for c in long_ones)
    assert all(c.kind == "merged" and "not seen" in c.reason for c in long_ones)
    # no trusted cycle, so no stroke rate is reported at all (before: a "reliable" 16.7/min)
    assert all(np.isnan(r) for r in found.rate_per_min.values())


def test_a_short_gap_that_cannot_hide_a_stroke_leaves_the_cycle_trusted():
    t = times(300)
    gap = round(0.25 * PERIOD * FPS)  # a quarter of a cycle, during the recovery
    start = round(3.6 * PERIOD * FPS)
    assert gap / (PERIOD * FPS) < MAX_UNSEEN_SHARE
    found = strokes(swimmer_xy(t, PERIOD, elbow_deg=120.0), [(start, start + gap, ARM_POINTS)])
    trusted = [c for c in found.cycles if c.trusted]
    assert len(trusted) >= len(found.cycles) - 2
    assert all(c.duration_s == pytest.approx(PERIOD, abs=0.05) for c in trusted)


def test_a_crossing_that_was_not_seen_marks_the_joined_cycle_as_merged():
    t = times(300)
    xy = swimmer_xy(t, PERIOD, elbow_deg=120.0)
    # hide only the left wrist around one mid-pull (the arm is seen in front, then already back)
    mid = round((2 + 0.25) * PERIOD * FPS)
    found = strokes(xy, [(mid - 6, mid + 6, [L_WRIST])])
    left = [c for c in found.cycles if c.arm == "left"]
    joined = [c for c in left if c.duration_s > 1.5 * PERIOD]
    assert len(joined) == 1 and not joined[0].trusted and joined[0].kind == "merged"
    assert all(c.trusted for c in left if c is not joined[0])


def test_changing_elbow_bend_does_not_change_the_measured_rhythm():
    found = strokes(alternating_elbow(times(360)))
    assert found.cycles and all(c.trusted and c.timing == "upper_arm" for c in found.cycles)
    durations = np.array([c.duration_s for c in found.cycles])
    # before: 1.31 s and 1.09 s alternating, from the wrist; the shoulder turns steadily
    assert durations == pytest.approx(PERIOD, abs=0.03)
    assert all(r == pytest.approx(60 / PERIOD, abs=1.0) for r in found.rate_per_min.values())


def test_a_really_uneven_rhythm_is_still_measured_as_uneven():
    t = times(360)
    lengths = np.array([1.0, 1.4] * 12) * PERIOD
    edges = np.concatenate([[0.0], np.cumsum(lengths)])
    i = np.clip(np.searchsorted(edges, t, side="right") - 1, 0, len(lengths) - 1)
    warped = (i + (t - edges[i]) / lengths[i]) * PERIOD
    found = strokes(swimmer_xy(warped, PERIOD, elbow_deg=120.0))
    left = np.array([c.duration_s for c in found.cycles if c.arm == "left" and c.trusted])
    assert len(left) >= 6
    assert left.max() - left.min() > 0.2  # the long and the short cycles are still told apart


def test_without_a_usable_elbow_the_wrist_is_used_for_every_cycle_of_that_arm():
    t = times(300)
    found = strokes(swimmer_xy(t, PERIOD, elbow_deg=120.0), [(0, 300, [L_ELBOW])])
    left = [c for c in found.cycles if c.arm == "left"]
    right = [c for c in found.cycles if c.arm == "right"]
    assert left and all(c.timing == "wrist" for c in left)
    assert right and all(c.timing == "upper_arm" for c in right)
    assert all(c.duration_s == pytest.approx(PERIOD, abs=0.05) for c in left if c.trusted)


def test_a_cycles_boundaries_and_its_duration_come_from_the_same_event():
    """End minus start is the duration, to the frame, whichever event the cycle is timed
    from, including when the elbow bend changes from stroke to stroke."""
    for found in (strokes(alternating_elbow(times(360))), strokes(swimmer_xy(times(300), PERIOD))):
        assert found.cycles
        for c in found.cycles:
            assert (c.end - c.start) / FPS == pytest.approx(c.duration_s, abs=1.0 / FPS)
