import numpy as np
import synthetic
from conftest import SWIM_FRAMES, make_raw_pose

from aquatrack.analysis.pipeline import analyze
from aquatrack.analysis.pose import cleanup
from aquatrack.analysis.processing import find_segments, process
from aquatrack.analysis.quality import build_quality_report
from aquatrack.contracts import (
    JointState,
    ProcessedPose,
    QualityGrade,
    RawPose,
    RejectReason,
    SessionInfo,
    VideoIdentity,
)

L_WRIST, R_KNEE = 9, 14
VIDEO = VideoIdentity(
    sha256="a" * 64,
    frame_count=SWIM_FRAMES,
    fps=synthetic.FPS,
    width=synthetic.W,
    height=synthetic.H,
)
FREESTYLE = SessionInfo(stroke="Freestyle", camera="Underwater")


def with_other_person(raw, start, end, dx=-0.6, dy=0.3):
    """Frames [start, end) show someone else, far from the swimmer."""
    raw.keypoints[start:end, :, 0] = np.clip(raw.keypoints[start:end, :, 0] + dx, 0, 1)
    raw.keypoints[start:end, :, 1] += dy
    shift = np.array([dx * raw.meta.width, dy * raw.meta.height] * 2)
    raw.boxes[start:end] += shift
    return raw


def test_clean_clip_is_all_observed_and_good():
    result, pose = analyze(make_raw_pose(), "v", FREESTYLE, VIDEO)
    assert (pose.state[:, 5:17] == JointState.OBSERVED).all()
    q = result.quality
    assert q.grade is QualityGrade.GOOD
    assert (q.valid_pose_pct, q.observed_pct, q.interpolated_pct) == (100.0, 100.0, 0.0)
    assert q.tracking.recorded and q.tracking.detected_pct == 100.0
    assert q.total_frames == SWIM_FRAMES and q.analyzed_frames == SWIM_FRAMES
    assert result.stroke.measurable and result.stroke.cycle_count == {"left": 7, "right": 7}
    assert result.stroke.cycles_per_min == {"left": 50.0, "right": 50.0}
    assert {m.key: m.value for m in result.measurements}["stroke_rate"] == 50.0


def test_short_gap_is_interpolated_and_marked_with_low_confidence():
    raw = make_raw_pose()
    gap = slice(60, 64)  # 4 frames at 25 fps = 0.16 s, under the 0.2 s limit
    raw.keypoints[gap, L_WRIST] = np.nan
    pose = process(raw).pose
    assert (pose.state[gap, L_WRIST] == JointState.INTERPOLATED).all()
    assert (pose.reasons[gap, L_WRIST] & RejectReason.FILLED).all()
    assert np.isfinite(pose.xy[gap, L_WRIST]).all()
    assert pose.confidence[gap, L_WRIST].max() <= cleanup.FILLED_CONFIDENCE
    assert pose.state[59, L_WRIST] == JointState.OBSERVED


def test_long_gap_stays_missing():
    raw = make_raw_pose()
    gap = slice(60, 80)  # 0.8 s
    raw.keypoints[gap, R_KNEE] = np.nan
    pose = process(raw).pose
    assert (pose.state[gap, R_KNEE] == JointState.MISSING).all()
    assert np.isnan(pose.xy[gap, R_KNEE]).all() and (pose.confidence[gap, R_KNEE] == 0).all()


def test_low_score_and_spike_points_are_rejected_not_kept():
    raw = make_raw_pose()
    raw.keypoints[100:130, L_WRIST, 2] = 1.0  # model unsure for over a second
    raw.keypoints[180, R_KNEE, :2] += 0.4  # one-frame jump
    pose = process(raw).pose
    assert (pose.state[105:125, L_WRIST] == JointState.REJECTED).all()
    assert (pose.reasons[105:125, L_WRIST] & RejectReason.LOW_SCORE).all()
    assert pose.reasons[180, R_KNEE] & (RejectReason.SPIKE | RejectReason.IMPOSSIBLE)
    # whatever happens next (left out, or filled from its neighbours), it is never "observed"
    assert pose.state[180, R_KNEE] in (JointState.REJECTED, JointState.INTERPOLATED)


def test_a_switch_to_another_person_is_cut_out_not_blended_in():
    raw = with_other_person(make_raw_pose(), 100, 120)
    segments = find_segments(raw)
    assert [(s.start, s.end, s.accepted) for s in segments] == [
        (0, 99, True),
        (100, 119, False),
        (120, 249, True),
    ]
    pose = process(raw).pose
    inside = pose.state[100:120]
    assert (inside == JointState.REJECTED).all()
    assert (pose.reasons[100:120] & RejectReason.OTHER_SWIMMER).all()
    assert np.isnan(pose.xy[100:120]).all()  # nothing interpolated or smoothed across it
    # the swimmer's own frames right next to the switch are untouched by the other person
    clean = process(make_raw_pose()).pose
    np.testing.assert_allclose(pose.xy[90:97], clean.xy[90:97], atol=1e-6)
    np.testing.assert_allclose(pose.xy[124:130], clean.xy[124:130], atol=1e-6)


def test_a_two_frame_switch_is_not_bridged_by_interpolation():
    raw = with_other_person(make_raw_pose(), 100, 102)  # shorter than the 0.2 s fill limit
    pose = process(raw).pose
    # the gap may be filled from the swimmer's own neighbouring frames, never from the other person
    clean = process(make_raw_pose()).pose
    filled = pose.state[100:102, 5:17] == JointState.INTERPOLATED
    assert filled.all()
    assert np.abs(pose.xy[100:102, 5:17] - clean.xy[100:102, 5:17]).max() < 0.25 * synthetic.TRUNK


def test_quality_counts_and_longest_missing_interval():
    raw = make_raw_pose()
    raw.keypoints[50:100] = np.nan  # swimmer out of view for 2 s
    raw.boxes[50:100] = np.nan
    raw.box_source[50:100] = 0
    result, pose = analyze(raw, "v", FREESTYLE, VIDEO)
    q = result.quality
    assert q.frames_with_swimmer == 200 and q.valid_pose_frames == 200
    assert q.valid_pose_pct == 80.0 and q.missing_pct == 20.0
    assert q.longest_missing_s == 2.0
    assert q.tracking.no_box_pct == 20.0
    assert q.per_joint_coverage["left_wrist"] == 80.0
    assert set(q.body_part_coverage) == {"head", "trunk", "arms", "legs", "hands", "feet"}


def test_grade_is_limited_when_someone_else_was_followed_for_a_while():
    result, _ = analyze(with_other_person(make_raw_pose(), 100, 120), "v", FREESTYLE, VIDEO)
    assert result.quality.grade is QualityGrade.LIMITED
    assert result.quality.tracking.other_swimmer_pct == 8.0
    assert result.quality.tracking.identity_breaks == 2
    assert any("followed someone else" in r for r in result.quality.grade_reasons)


def test_empty_clip_is_insufficient_and_reports_no_numbers():
    raw = make_raw_pose()
    raw.keypoints[:] = np.nan
    result, _ = analyze(raw, "v", FREESTYLE, VIDEO)
    assert result.quality.grade is QualityGrade.INSUFFICIENT
    assert not result.stroke.measurable and result.stroke.stroke_count is None
    assert result.measurements == []
    assert result.unavailable[0].key == "stroke_rate"


def test_numbers_are_withheld_when_the_clip_is_insufficient():
    raw = make_raw_pose()
    raw.keypoints[80:] = np.nan  # 3.2 s of swimmer in a 10 s clip: under 40% valid
    result, _ = analyze(raw, "v", FREESTYLE, VIDEO)
    assert result.quality.grade is QualityGrade.INSUFFICIENT
    assert not result.stroke.measurable and result.measurements == []
    assert "could not be followed reliably" in result.stroke.reason


def test_grade_does_not_depend_on_the_filming_angle():
    above = SessionInfo(stroke="Freestyle", camera="Side (deck level)")
    result, _ = analyze(make_raw_pose(), "v", above, VIDEO)
    assert result.quality.grade is QualityGrade.GOOD  # same data, same grade
    assert any("has not been validated" in n for n in result.quality.filming_limitations)
    under, _ = analyze(make_raw_pose(), "v", FREESTYLE, VIDEO)
    assert under.quality.filming_limitations != result.quality.filming_limitations


def test_breaststroke_cycles_are_reported_as_unavailable():
    result, _ = analyze(make_raw_pose(), "v", SessionInfo(stroke="Breaststroke"), VIDEO)
    assert not result.stroke.measurable and "breaststroke" in result.stroke.reason
    assert result.quality.reliable_stroke_cycles == 0


def test_pending_measures_are_listed_with_reasons_not_invented():
    result, _ = analyze(make_raw_pose(), "v", FREESTYLE, VIDEO)
    keys = {u.key for u in result.unavailable}
    assert {"head_position", "body_alignment", "kick_rhythm", "body_rotation"} <= keys
    assert all(u.reason for u in result.unavailable)
    assert {m.key for m in result.measurements} == {"stroke_rate", "cycle_duration", "stroke_count"}


def test_stroke_count_is_withheld_when_some_cycles_were_unclear():
    raw = make_raw_pose()
    raw.keypoints[100:140, [9, 10]] = (
        np.nan
    )  # both wrists hidden for 1.6 s: cycles there are unsure
    result, _ = analyze(raw, "v", FREESTYLE, VIDEO)
    assert result.stroke.measurable and result.stroke.stroke_count is None
    assert any(not c.trusted for c in result.stroke.cycles)
    assert "stroke_count" not in {m.key for m in result.measurements}
    assert {m.key for m in result.measurements} == {"stroke_rate", "cycle_duration"}
    assert result.unavailable[0].key == "stroke_count" and "too low" in result.unavailable[0].reason


def test_processed_pose_round_trip_and_separate_from_raw(tmp_path):
    raw = make_raw_pose()
    before = raw.keypoints.copy()
    pose = process(raw).pose
    np.testing.assert_array_equal(raw.keypoints, before)  # raw data is never edited
    back = ProcessedPose.load(pose.save(tmp_path / "p.npz"))
    np.testing.assert_array_equal(back.state, pose.state)
    assert back.meta.processing["max_gap_s"] == cleanup.MAX_GAP_S == 0.2


def test_quality_report_for_legacy_pose_says_tracking_was_not_recorded(tmp_path):
    seq = synthetic.to_sequence(synthetic.swimmer_xy(synthetic.times(SWIM_FRAMES)))
    raw = RawPose.load(seq.save(tmp_path / "clip.wholebody.npz"))
    pose = process(raw).pose
    q = build_quality_report(raw, pose, 14, FREESTYLE, SWIM_FRAMES)
    assert not q.tracking.recorded and q.tracking.detected_pct is None
    assert q.valid_pose_pct == 100.0
