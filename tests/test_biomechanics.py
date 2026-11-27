"""Metrics, their reliability, arm usability and the camera side, on synthetic swimmers
with known geometry. None of this is real-video validation."""

import numpy as np
import pytest
import synthetic
from conftest import SWIM_FRAMES, make_raw_pose

from aquatrack.analysis import biomechanics
from aquatrack.analysis.metrics.cycles import analyze_strokes
from aquatrack.analysis.pipeline import analyze
from aquatrack.analysis.processing import process
from aquatrack.analysis.usability import ArmFrame, arm_use, camera_side, view_check
from aquatrack.contracts import (
    ANALYSIS_SCHEMA_VERSION,
    AnalysisResult,
    MetricSample,
    MetricStatus,
    QualityGrade,
    SessionInfo,
    VideoIdentity,
)

FREESTYLE = SessionInfo(stroke="Freestyle", camera="Underwater")
VIDEO = VideoIdentity(
    sha256="a" * 64,
    frame_count=SWIM_FRAMES,
    fps=synthetic.FPS,
    width=synthetic.W,
    height=synthetic.H,
    duration_s=SWIM_FRAMES / synthetic.FPS,
)
T = synthetic.times(SWIM_FRAMES)


def side_view(far: str = "left", recovery: bool = True, **kwargs) -> np.ndarray:
    """A swimmer heading right as an underwater side camera gives it: the far arm is lost
    behind the body past 115 degrees, and (as the pose model does on real clips) both arms
    are drawn swinging back to the front under the body while they are really in the air."""
    xy = synthetic.swimmer_xy(T, **kwargs)
    period = kwargs.get("period", 1.2)
    for arm, offset in (("left", 0.0), ("right", 0.5 + 0.3 / (2 * np.pi))):
        phase = (T / period + offset) % 1.0
        back = 115 if arm == far else 180  # how far back the arm is seen
        pull = np.minimum(phase / 0.5 * 180, back)  # front -> back in the first half
        drawn = back * (1 - (phase - 0.5) / 0.5) if recovery else np.full(len(T), 5.0)
        synthetic.set_arm(xy, arm, np.where(phase < 0.5, pull, drawn))
    return xy


def run(xy=None, session=FREESTYLE, **changes):
    raw = make_raw_pose(xy=xy)
    for name, value in changes.items():
        setattr(raw, name, value)
    result, _ = analyze(raw, "v", session, VIDEO)
    return result, {m.key: m for m in result.metrics}


# ---------- camera side ----------


def test_camera_side_needs_direction_and_footage_to_agree():
    result, _ = run(side_view(far="left"))
    side = result.coverage.camera_side
    assert side.arm == "right" and len(side.evidence) >= 2  # heading right, face down
    assert "followed further back" in " ".join(side.evidence)


def test_camera_side_is_not_assumed_when_both_arms_look_the_same():
    result, m = run()  # both arms fully visible: nothing in the footage tells them apart
    side = result.coverage.camera_side
    assert side.arm is None and "does not show clearly" in side.reason
    for key in ("pull_depth", "elbow_angle_min", "pull_path_variation"):
        assert m[key].status is MetricStatus.UNAVAILABLE and m[key].value is None
        assert "nearer" in m[key].reason
    # Timing does not need to know the side.
    assert m["stroke_rate"].status is MetricStatus.RELIABLE


def test_camera_side_is_refused_when_direction_and_footage_disagree():
    # Heading right says "right arm", but it is the right arm that is hidden: mirrored video
    # or swapped labels. Either way the side is not established.
    result, m = run(side_view(far="right"))
    assert result.coverage.camera_side.arm is None
    assert "disagree" in result.coverage.camera_side.reason
    assert m["pull_depth"].status is MetricStatus.UNAVAILABLE


def test_backstroke_faces_the_other_side_and_other_views_are_not_guessed():
    raw = make_raw_pose(xy=side_view(far="right"))
    clean = process(raw).clean
    strokes = analyze_strokes(clean)
    back = camera_side(clean, raw.keypoints, strokes, SessionInfo(stroke="Backstroke"))
    assert back.arm == "left"
    overhead = camera_side(clean, raw.keypoints, strokes, SessionInfo(camera="Overhead"))
    assert overhead.arm is None and "underwater side views" in overhead.reason


def test_both_arms_stay_in_the_pose_data():
    raw = make_raw_pose(xy=side_view())
    processed = process(raw)
    assert np.isfinite(processed.pose.xy[:, [9, 10]]).all()  # nothing removed, only not used


# ---------- hidden arms ----------


def test_points_drawn_during_the_recovery_are_not_used_and_are_reported():
    xy = side_view(far="left")
    raw = make_raw_pose(xy=xy)  # every point scores 6.0: the model is "sure" of all of them
    clean = process(raw).clean
    strokes = analyze_strokes(clean)
    use = arm_use(clean, strokes)["right"]

    phase = (T / 1.2 + 0.5 + 0.3 / (2 * np.pi)) % 1.0
    in_air = (phase > 0.55) & (phase < 0.85)  # the drawn backward swing under the body
    assert not use.followed[in_air].any()
    assert (use.kind[in_air] == ArmFrame.MODEL_ONLY).mean() > 0.9  # drawn, not backed up
    assert use.followed[(phase > 0.1) & (phase < 0.45)].mean() > 0.9  # the real pull

    result, m = run(xy)
    near = next(a for a in result.coverage.arms if a.camera_side)
    assert near.arm == "right" and near.model_only_pct > 15 and near.supported_pct > 30
    # The drawn recovery does not change what the pull measures: a straight arm, pulled
    # one arm's length (1.3 trunk lengths) deep.
    assert m["pull_depth"].value == pytest.approx(1.3, abs=0.05)
    assert m["elbow_angle_min"].value == pytest.approx(180, abs=3)
    assert m["stroke_rate"].value == pytest.approx(50, abs=1)


def test_far_arm_is_never_measured_for_arm_shape():
    _, m = run(side_view(far="left"))
    assert {m[k].side for k in ("pull_depth", "elbow_angle_min", "pull_path_variation")} == {
        "right"
    }
    assert m["elbow_angle_min"].status is MetricStatus.LIMITED  # a picture angle, always
    assert "not the true joint angle" in m["elbow_angle_min"].reason


def test_interpolated_points_do_not_feed_metrics():
    xy = side_view()
    raw = make_raw_pose(xy=xy)
    raw.keypoints[60:64, :, 2] = 1.0  # a 0.16 s gap that cleanup fills by interpolation
    result, m = analyze(raw, "v", FREESTYLE, VIDEO)
    assert result.quality.interpolated_pct > 0
    head = next(x for x in result.metrics if x.key == "head_height")
    assert head.coverage_pct < 100  # the filled frames were left out, not used


# ---------- body metrics with known geometry ----------


def test_body_metrics_on_a_flat_swimmer_are_zero():
    _, m = run(side_view(travel=1.0))
    assert m["leg_line_angle"].value == pytest.approx(0, abs=1.5)
    assert m["body_line_angle"].value == pytest.approx(0, abs=1.5)
    assert m["leg_line_angle"].status is MetricStatus.RELIABLE
    assert m["body_line_angle"].status is MetricStatus.RELIABLE  # level from the hip path
    assert m["head_height"].value == pytest.approx(0, abs=0.03)
    assert m["leg_line_angle"].coverage_pct == 100


def test_dropped_hips_show_as_legs_above_the_trunk_line():
    # Hips 0.2 trunk lengths below the shoulders; the legs run level behind them.
    _, m = run(side_view(hip_drop=0.2, travel=1.0))
    trunk_tilt = np.degrees(np.arctan2(0.2, 1.0))
    assert m["leg_line_angle"].value == pytest.approx(-trunk_tilt, abs=1.5)
    assert m["head_height"].value < -0.05  # face points level with the shoulders: below the line


def test_body_line_is_limited_without_a_level_reference():
    _, m = run(side_view())  # no travel in the picture, no video for pool lines
    assert m["body_line_angle"].status is MetricStatus.LIMITED
    assert "tilted camera" in m["body_line_angle"].reason
    assert m["leg_line_angle"].status is MetricStatus.RELIABLE  # needs no level reference


def test_every_metric_carries_its_own_evidence():
    result, m = run(side_view(travel=1.0))
    for metric in result.metrics:
        assert metric.description and metric.limitations
        if metric.status is MetricStatus.UNAVAILABLE:
            assert metric.value is None and metric.reason and not metric.samples
        else:
            assert metric.value is not None and metric.n_cycles >= 1 and metric.basis
            assert all(0 <= s.t_s <= 10 for s in metric.samples)
        if metric.status is MetricStatus.LIMITED:
            assert metric.reason
    assert m["leg_line_angle"].samples[0].start_s < m["leg_line_angle"].samples[0].end_s


# ---------- reliability rules ----------


def test_too_few_cycles_is_limited_and_rhythm_unavailable():
    xy = side_view(period=3.0)  # 10 s clip: 2 whole cycles of the near arm
    _, m = run(xy)
    assert m["stroke_rate"].status is MetricStatus.LIMITED
    assert "Only 2 stroke cycles" in m["stroke_rate"].reason
    assert m["rhythm_variation"].status is MetricStatus.UNAVAILABLE
    assert "at least 3" in m["rhythm_variation"].reason


def test_low_joint_coverage_limits_only_the_metric_that_needs_those_joints():
    raw = make_raw_pose(xy=side_view())
    hidden = np.arange(SWIM_FRAMES) % 10 < 4  # ankles lost 40% of the time, in long runs
    raw.keypoints[np.ix_(hidden, [15, 16])] = np.nan
    result, _ = analyze(raw, "v", FREESTYLE, VIDEO)
    m = {x.key: x for x in result.metrics}
    assert m["leg_line_angle"].status is MetricStatus.LIMITED
    assert "usable in" in m["leg_line_angle"].reason
    assert m["head_height"].status is MetricStatus.RELIABLE
    assert m["stroke_rate"].status is MetricStatus.RELIABLE


def test_steady_drift_through_the_clip_is_flagged():
    def samples(values):
        return [MetricSample(t_s=float(i), value=float(v)) for i, v in enumerate(values)]

    assert biomechanics.drifts(samples([-20, -16, -9, -8, -7, -3, -1]))
    assert not biomechanics.drifts(samples([-8, -9, -7, -8, -9, -8, -7]))
    assert not biomechanics.drifts(samples([1, 2, 3]))  # too few to call a trend


def test_a_trend_is_not_decided_by_differences_the_measurement_cannot_tell_apart():
    """From the first local model run (2026-11-28): two poses of one clip a few pixels apart
    gave leg-line values of [-8.2, -7.9, -9.9, -11.2] and [-8.1, -8.3, -10.5, -11.2] degrees.
    The order of the first two (0.3 degrees apart, resolution 2 degrees) moved the rank
    correlation between 1.0 and 0.8, the cut-off, where floating point then decided: one clip
    came out "reliable" and the other "limited". Both now get the same answer, and neither
    is a trend: the whole change is under twice the resolution."""

    def samples(values):
        return [MetricSample(t_s=float(i), value=v) for i, v in enumerate(values)]

    one, other = samples([-8.2, -7.9, -9.9, -11.2]), samples([-8.1, -8.3, -10.5, -11.2])
    resolution = biomechanics.RESOLUTION["leg_line_angle"]
    assert biomechanics.drifts(one, resolution) is False
    assert biomechanics.drifts(other, resolution) is False
    # exactly at the cut-off is now decided the same way every time
    assert biomechanics.drifts(one) is biomechanics.drifts(samples([-8.2, -7.9, -9.9, -11.2]))
    # head height: three equal values and one apart is not a steady trend, either way round
    head = biomechanics.RESOLUTION["head_height"]
    assert not biomechanics.drifts(samples([-0.08, -0.0, -0.0, -0.01]), head)
    assert not biomechanics.drifts(samples([-0.08, 0.0, -0.0, -0.0]), head)
    # a change well beyond the resolution is still a trend, ties or not
    assert biomechanics.drifts(samples([-8.0, -8.5, -14.0, -19.0]), resolution)
    assert biomechanics.drifts(samples([0.0, 0.2, 0.4, 0.6]), head)
    # and a value that wanders without direction is not
    assert not biomechanics.drifts(samples([-8.0, -15.0, -9.0, -16.0]), resolution)


def test_other_strokes_and_views_are_held_at_limited():
    _, m = run(side_view(), SessionInfo(stroke="Butterfly", camera="Underwater"))
    assert m["stroke_rate"].status is MetricStatus.LIMITED
    assert "freestyle" in m["stroke_rate"].reason
    _, m = run(side_view(), SessionInfo(stroke="Freestyle", camera="Overhead"))
    assert m["cycle_duration"].status is MetricStatus.LIMITED
    assert m["pull_depth"].status is MetricStatus.UNAVAILABLE  # no camera side from overhead


def test_nothing_is_measured_when_tracking_is_insufficient_or_stroke_unsupported():
    raw = make_raw_pose(xy=side_view())
    raw.keypoints[80:] = np.nan
    result, _ = analyze(raw, "v", FREESTYLE, VIDEO)
    assert result.quality.grade is QualityGrade.INSUFFICIENT
    assert all(m.status is MetricStatus.UNAVAILABLE and m.value is None for m in result.metrics)
    assert result.coverage.metrics_reliable == 0 and result.coverage.cycles.status == "none"

    result, _ = run(side_view(), SessionInfo(stroke="Breaststroke"))
    assert all(m.status is MetricStatus.UNAVAILABLE for m in result.metrics)
    assert "breaststroke" in result.metrics[0].reason


# ---------- counts and sections ----------


def test_count_is_given_only_when_every_cycle_and_the_edges_are_accounted_for():
    result, m = run(side_view())
    assert m["cycle_count"].status is MetricStatus.RELIABLE and m["cycle_count"].value == 7
    assert result.stroke.counted_arm == "right" and result.stroke.counted_cycles == 7
    assert result.coverage.cycles.status == "complete"
    assert len(result.stroke.partial) >= 1  # part-cycles at the edges are listed, not counted

    # The same clip with the near arm's last two pulls not seen: 2.4 s of swimming after
    # the last pull that was followed, so a count would be too low.
    raw = make_raw_pose(xy=side_view())
    raw.keypoints[190:, 10] = np.nan
    result, _ = analyze(raw, "v", FREESTYLE, VIDEO)
    count = next(x for x in result.metrics if x.key == "cycle_count")
    assert count.status is MetricStatus.UNAVAILABLE and "a pull was missed" in count.reason
    assert result.coverage.cycles.status == "partial"
    rate = next(x for x in result.metrics if x.key == "stroke_rate")
    assert rate.status is MetricStatus.RELIABLE  # timing survives without the count


def test_sections_are_compared_only_with_enough_cycles_in_each_third():
    _, m = run(side_view())  # 7 cycles in 10 s: 2 or 3 per third
    assert m["cycle_time_change"].status is MetricStatus.UNAVAILABLE
    assert "too short" in m["cycle_time_change"].reason

    _, m = run(side_view(period=0.8))  # 11 cycles: 3 or 4 per third
    change = m["cycle_time_change"]
    assert change.status is MetricStatus.LIMITED  # an even swimmer: no clear change
    assert change.value == pytest.approx(0, abs=0.03) and "no clear change" in change.reason
    assert [s.label for s in change.samples] == ["start", "middle", "end"]
    assert any("fatigue" in text for text in change.limitations)


# ---------- quality levels and schema ----------


def test_tracking_grade_and_analysis_coverage_are_separate():
    raw = make_raw_pose(xy=side_view())
    raw.keypoints[100:140, [9, 10]] = np.nan  # wrists hidden for 1.6 s
    result, _ = analyze(raw, "v", FREESTYLE, VIDEO)
    assert result.quality.grade is QualityGrade.GOOD
    assert not any("cycle" in r for r in result.quality.grade_reasons)
    c = result.coverage
    assert c.tracking_grade is QualityGrade.GOOD
    assert c.cycles.status == "partial" and c.cycles.ambiguous >= 1
    assert c.metrics_reliable + c.metrics_limited + c.metrics_unavailable == len(result.metrics)
    assert {a.arm for a in c.arms} == {"left", "right"}


def test_schema_adds_fields_and_older_documents_still_load():
    result, _ = run(side_view())
    assert result.schema_version == ANALYSIS_SCHEMA_VERSION == "1.2"
    doc = result.to_firestore()
    assert doc["metrics"] and doc["coverage"]["cycles"]["arm"] == "right"
    # A Phase 1 document: no metrics, no coverage, no cycle kinds.
    old = {k: v for k, v in doc.items() if k not in ("metrics", "coverage")}
    old["schema_version"] = "1.0"
    for cycle in old["stroke"]["cycles"]:
        cycle.pop("kind")
    for key in ("partial", "counted_arm", "counted_cycles"):
        old["stroke"].pop(key)
    loaded = AnalysisResult.model_validate(old)
    assert loaded.schema_version == "1.0" and loaded.metrics == [] and loaded.coverage is None
    assert loaded.measurements == result.measurements


# ---------- Phase 2 refinement: regressions found on real video ----------

NEAR_PHASE = (T / 1.2 + 0.5 + 0.3 / (2 * np.pi)) % 1.0  # the right arm's phase in side_view()


def _move_forearm(xy: np.ndarray, frames: np.ndarray, share: np.ndarray | float, bend_deg=0.0):
    """Redraw the right forearm at `share` of its length, turned `bend_deg` at the elbow."""
    upper = xy[frames, 8] - xy[frames, 6]
    forearm = synthetic._rotate(upper, bend_deg) * np.reshape(share, (-1, 1))
    xy[frames, 10] = xy[frames, 8] + forearm
    for k, p in enumerate(synthetic.RIGHT_HAND):
        xy[frames, p] = xy[frames, 10] + forearm * 0.4 * (k / 20)


def test_wrist_pulled_up_against_the_elbow_does_not_enter_the_elbow_angle():
    # Sprint clip, 5.92 s: as the hand leaves the water the model draws the wrist just under
    # the elbow, confident scores. Unchecked, that frame became the pull's "smallest elbow angle".
    xy = side_view()
    late = np.nonzero((NEAR_PHASE > 0.40) & (NEAR_PHASE < 0.5))[0]
    _move_forearm(xy, late, 0.25, bend_deg=80)
    raw = make_raw_pose(xy=xy)
    before = raw.keypoints.copy()

    result, _ = analyze(raw, "v", FREESTYLE, VIDEO)
    m = {x.key: x for x in result.metrics}

    assert m["elbow_angle_min"].value == pytest.approx(180, abs=5)  # not 100
    assert "impossibly short" in m["elbow_angle_min"].basis
    assert m["elbow_angle_min"].coverage_pct < 95  # the frames are missing from the evidence
    near = next(a for a in result.coverage.arms if a.camera_side)
    assert near.model_only_collapsed_pct > 3
    np.testing.assert_array_equal(raw.keypoints, before)  # the pose data is untouched
    assert m["stroke_rate"].value == pytest.approx(50, abs=1)  # cycles are still found


def test_an_arm_that_only_looks_shorter_is_still_measured():
    # Pointing partly toward the camera, the forearm shortens smoothly to 60% of its length
    # in the middle of each pull. That is perspective, not a wrong point.
    xy = side_view()
    pulling = np.nonzero(NEAR_PHASE < 0.5)[0]
    share = 1 - 0.4 * np.sin(np.pi * NEAR_PHASE[pulling] / 0.5)
    _move_forearm(xy, pulling, share)
    raw = make_raw_pose(xy=xy)
    clean = process(raw).clean
    use = arm_use(clean, analyze_strokes(clean))["right"]

    assert not use.collapsed.any()
    assert use.followed[(NEAR_PHASE > 0.1) & (NEAR_PHASE < 0.45)].mean() > 0.9
    result, _ = analyze(raw, "v", FREESTYLE, VIDEO)
    m = {x.key: x for x in result.metrics}
    assert m["pull_depth"].status is MetricStatus.RELIABLE
    assert "impossibly short" not in m["pull_depth"].basis


def test_an_elbow_value_no_neighbouring_frame_agrees_with_is_dropped():
    from aquatrack.analysis.metrics.technique import _agrees_with_neighbours

    frames = np.arange(10, 20)
    values = np.array([170, 168, 165, 160, 95, 150, 145, 140, 138, 135.0])  # one frame at 95
    keep = _agrees_with_neighbours(frames, values)
    assert not keep[4] and keep.sum() == 9
    steady_bend = np.linspace(170, 100, 10)  # a real, gradual bend is kept whole
    assert _agrees_with_neighbours(frames, steady_bend).all()
    assert not _agrees_with_neighbours(np.array([5]), np.array([120.0])).any()  # nothing to agree


def test_an_arm_drawn_in_front_is_a_model_prediction_not_a_confirmed_reach():
    xy = side_view(recovery=False)  # between pulls the arm is drawn stretched ahead
    raw = make_raw_pose(xy=xy)
    clean = process(raw).clean
    use = arm_use(clean, analyze_strokes(clean))["right"]
    ahead = (NEAR_PHASE > 0.6) & (NEAR_PHASE < 0.9)

    assert (use.kind[ahead] == ArmFrame.MODEL_ONLY).all() and use.in_front[ahead].all()
    assert not use.followed[ahead].any()
    result, _ = analyze(raw, "v", FREESTYLE, VIDEO)
    near = next(a for a in result.coverage.arms if a.camera_side)
    assert near.model_only_in_front_pct > 20
    assert near.model_only_in_front_pct <= near.model_only_pct
    # Only a followed pull counts as supported, however confident the model is elsewhere.
    assert near.supported_pct < 60 and (raw.keypoints[:, 10, 2] == 6.0).all()


def test_arm_classes_are_exclusive_and_interpolated_points_are_counted_as_such():
    xy = side_view()
    raw = make_raw_pose(xy=xy)
    in_pull = np.nonzero((NEAR_PHASE > 0.2) & (NEAR_PHASE < 0.3))[0][:3]  # 3 frames, mid-pull
    raw.keypoints[in_pull, 10, 2] = 1.0  # the right wrist's score drops: cleanup fills the gap
    clean = process(raw).clean
    use = arm_use(clean, analyze_strokes(clean))["right"]

    assert (use.kind[in_pull] == ArmFrame.INTERPOLATED).all()  # not MODEL_ONLY, not SUPPORTED
    result, _ = analyze(raw, "v", FREESTYLE, VIDEO)
    for arm in result.coverage.arms:
        parts = [
            arm.supported_pct,
            arm.interpolated_pct,
            arm.model_only_pct,
            arm.rejected_pct,
            arm.missing_pct,
        ]
        assert all(p is not None and p >= 0 for p in parts)
        assert sum(parts) == pytest.approx(100, abs=0.11)
    near = next(a for a in result.coverage.arms if a.camera_side)
    assert near.interpolated_pct == pytest.approx(100 * 3 / SWIM_FRAMES, abs=0.5)


def _shrunk(xy: np.ndarray, frames: slice, scale: float) -> np.ndarray:
    """The swimmer drawn smaller in some frames: further away and seen at an angle."""
    out = xy.copy()
    out[frames] = synthetic.HIP + (xy[frames] - synthetic.HIP) * scale
    return out


def test_cycles_filmed_at_an_angle_are_left_out_of_picture_measurements_only():
    # A camera the swimmer swims past: small at first (seen at an angle), full size later.
    xy = _shrunk(side_view(), slice(0, 100), 0.65)
    raw = make_raw_pose(xy=xy)
    result, _ = analyze(raw, "v", FREESTYLE, VIDEO)
    m = {x.key: x for x in result.metrics}
    view = result.coverage.view

    assert view.status == "changing" and view.cycles_left_out >= 2
    assert view.smallest_size_share == pytest.approx(0.65, abs=0.05)
    assert "at an angle" in view.note
    for key in ("leg_line_angle", "head_height", "body_line_angle", "pull_depth"):
        assert m[key].excluded_cycles >= 2, key
        assert m[key].n_cycles < m["cycle_duration"].n_cycles, key
        assert all(s.start_s >= 3.5 for s in m[key].samples), key  # none from the early part
        assert "seen at an angle" in m[key].basis
    # Timing does not depend on the view: every cycle still counts.
    assert m["stroke_rate"].status is MetricStatus.RELIABLE and m["cycle_duration"].n_cycles == 7
    assert m["stroke_rate"].excluded_cycles == 0


def test_a_steady_view_is_not_claimed_to_be_side_on_and_too_few_cycles_is_unknown():
    raw = make_raw_pose(xy=side_view())
    clean = process(raw).clean
    strokes = analyze_strokes(clean)
    steady = view_check(clean, [c for c in strokes.cycles if c.trusted])
    assert steady.status == "steady" and not steady.unsuitable
    assert view_check(clean, strokes.cycles[:1]).status == "unknown"

    # Almost the whole clip at an angle: what is left is too little for a reliable value.
    xy = _shrunk(side_view(), slice(0, 200), 0.65)
    result, _ = analyze(make_raw_pose(xy=xy), "v", FREESTYLE, VIDEO)
    m = {x.key: x for x in result.metrics}
    assert m["leg_line_angle"].status is not MetricStatus.RELIABLE
    assert m["leg_line_angle"].n_cycles <= 2


def test_documents_without_the_1_2_fields_still_load():
    result, _ = run(side_view())
    doc = result.to_firestore()
    doc["schema_version"] = "1.1"
    doc["coverage"].pop("view")
    for arm in doc["coverage"]["arms"]:
        for key in [k for k in arm if k.startswith(("supported", "interpolated", "model_only"))]:
            arm.pop(key)
        arm.pop("rejected_pct")
        arm.pop("missing_pct")
    for metric in doc["metrics"]:
        metric.pop("excluded_cycles")
    loaded = AnalysisResult.model_validate(doc)
    assert loaded.coverage.view is None and loaded.coverage.arms[0].supported_pct is None
    assert loaded.coverage.arms[0].followed_pct == result.coverage.arms[0].followed_pct
    assert loaded.metrics[0].excluded_cycles == 0


class _FlatGeometry:
    """Travel to the right, down is +y, trunk length 1: angles read straight off the points."""

    def tilt(self, vec):
        return np.degrees(np.arctan2(vec[:, 1], vec[:, 0]))

    def along(self, vec):
        return vec[:, 0]

    def depth(self, vec):
        return vec[:, 1]


def _catch_arm(upper_deg, forearm_from_down_deg):
    """Left arm (shoulder 5, elbow 7, wrist 9) frame by frame, from the upper arm's tilt
    below travel and the forearm's angle from straight down (positive: hand ahead)."""
    n = len(upper_deg)
    xy = np.full((n, 17, 2), np.nan)
    u, f = np.radians(upper_deg), np.radians(forearm_from_down_deg)
    xy[:, 5] = 0.0
    xy[:, 7] = np.stack([np.cos(u), np.sin(u)], axis=1)
    xy[:, 9] = xy[:, 7] + np.stack([np.sin(f), np.cos(f)], axis=1)
    return xy


def _cycle(pull_start, end):
    from aquatrack.analysis.metrics.cycles import StrokeCycle

    return StrokeCycle("left", 0, end, 0, 1.0, True, pull_start=pull_start)


def test_catch_is_read_where_the_upper_arm_crosses_the_mark_and_interpolated():
    upper = np.array([20, 30, 40, 50, 60, 70, 80, 90.0])
    forearm = np.array([60, 50, 40, 20, 10, 5, 0, 0.0])  # high elbow: forearm drops early
    xy = _catch_arm(upper, forearm)
    out = biomechanics.catch_angles(
        _FlatGeometry(), xy, "left", [_cycle(0, 7)], np.ones(8, bool), lambda i: i / 25
    )
    # 45 degrees falls halfway between frames 2 (40) and 3 (50): forearm 30 degrees.
    assert [s.value for s in out] == [30.0]


def test_catch_needs_the_pull_start_followed_and_supported_frames_either_side():
    upper = np.array([20, 30, 40, 50, 60, 70, 80, 90.0])
    xy = _catch_arm(upper, np.full(8, 10.0))
    g, sec = _FlatGeometry(), lambda i: i / 25
    hole = np.ones(8, bool)
    hole[[1, 2, 3, 4]] = False  # frames around the crossing not supported: gap of 5
    assert biomechanics.catch_angles(g, xy, "left", [_cycle(0, 7)], hole, sec) == []
    late = np.ones(8, bool)
    late[:4] = False  # first supported frame is already past the mark
    assert biomechanics.catch_angles(g, xy, "left", [_cycle(0, 7)], late, sec) == []
    assert biomechanics.catch_angles(g, xy, "left", [_cycle(None, 7)], np.ones(8, bool), sec) == []


def test_catch_metric_is_a_limited_picture_angle_for_the_near_arm_only():
    result, metrics = run(side_view(far="left"))
    m = metrics["catch_forearm_angle"]
    assert m.kind.value == "proxy"
    if m.status is not MetricStatus.UNAVAILABLE:
        assert m.status is MetricStatus.LIMITED
        assert m.side == result.coverage.camera_side.arm
