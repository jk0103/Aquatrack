from pathlib import Path

import cv2
import numpy as np
import pytest
from synthetic import FPS, H, W, swimmer_xy, times, to_sequence

from aquatrack.analysis.horizon import horizontal, line_angle
from aquatrack.analysis.keyframes import DRAWINGS, render_keyframes
from aquatrack.analysis.metrics.cycles import analyze_strokes
from aquatrack.analysis.metrics.technique import measure_technique, near_side
from aquatrack.analysis.pose.cleanup import clean


def measure(xy, **kwargs):
    pose = clean(to_sequence(xy))
    strokes = analyze_strokes(pose)
    frames = np.arange(len(pose))
    horizon, source = horizontal(pose, frames)
    return measure_technique(pose, strokes, horizon, source, **kwargs), pose, strokes


def median(report, name, **match):
    return report.measures[name].median(**match)


def test_straight_arms_known_geometry():
    report, _, _ = measure(swimmer_xy(times()))

    assert median(report, "cycle_time") == pytest.approx(1.2, abs=0.05)
    assert median(report, "elbow_min_pull") == pytest.approx(180, abs=3)
    # 1.3 at full reach; smoothing a fast circular path pulls it in slightly.
    assert median(report, "reach_ahead_of_shoulder") == pytest.approx(1.3, abs=0.05)
    assert median(report, "pull_depth") == pytest.approx(1.3, abs=0.05)
    # At the catch the upper arm is 30 deg below the travel line; a straight arm puts the
    # forearm 60 deg from vertical with the elbow 0.65 * sin(30) above the wrist.
    assert median(report, "catch_forearm_from_vertical") == pytest.approx(60, abs=4)
    assert median(report, "catch_elbow_above_wrist") == pytest.approx(0.325, abs=0.05)
    assert median(report, "body_line_angle") == pytest.approx(0, abs=1)
    assert median(report, "hip_depth_below_shoulders") == pytest.approx(0, abs=0.02)
    assert median(report, "kicks_per_cycle") == 0  # legs still
    for v in report.measures["elbow_min_pull"].values:
        assert v.confidence == 1.0 and v.side in ("left", "right") and len(v.curve) == 11


def test_bent_elbow_and_vertical_forearm_at_the_catch():
    report, _, _ = measure(swimmer_xy(times(), elbow_deg=120))

    assert median(report, "elbow_min_pull") == pytest.approx(120, abs=3)
    assert median(report, "elbow_mean_pull") == pytest.approx(120, abs=3)
    # Upper arm 30 deg down, forearm turned 60 deg more: straight down.
    assert median(report, "catch_forearm_from_vertical") == pytest.approx(0, abs=5)
    assert median(report, "catch_elbow_above_wrist") == pytest.approx(0.65, abs=0.05)


def test_six_beat_kick_size_knee_and_foot():
    # 2.5 Hz per leg, legs in opposition, 1.2 s arm cycle: 2 * 2.5 * 1.2 = 6 beats.
    report, _, _ = measure(swimmer_xy(times(), kick_hz=2.5, kick_amp=0.15, foot_deg=20))

    assert median(report, "kicks_per_cycle") == pytest.approx(6, abs=0.5)
    # 5th-95th percentile of a 0.15 sine is 0.285; cleanup's smoothing trims a 2.5 Hz kick
    # at 25 fps by about a fifth.
    assert median(report, "kick_size") == pytest.approx(0.285, rel=0.25)
    # Knee fixed 0.8 trunk ahead of the ankle, which moves 0.15 off the line.
    assert median(report, "knee_bend_max") == pytest.approx(
        np.degrees(np.arctan(0.15 / 0.8)), abs=3
    )
    assert median(report, "foot_point") == pytest.approx(20, abs=3)
    assert set(report.measures["foot_point"].summary()["by_side"]) == {"left", "right"}


def test_two_beat_kick():
    report, _, _ = measure(swimmer_xy(times(), kick_hz=1 / 1.2))
    assert median(report, "kicks_per_cycle") == pytest.approx(2, abs=0.5)


def test_hips_below_shoulders():
    report, _, _ = measure(swimmer_xy(times(), hip_drop=0.2))
    assert median(report, "hip_depth_below_shoulders") == pytest.approx(0.2, abs=0.03)


def test_tilted_camera_does_not_change_the_body_angle_when_the_hips_show_travel():
    still, _, _ = measure(swimmer_xy(times(), tilt_deg=8))
    moving, _, _ = measure(swimmer_xy(times(), tilt_deg=8, travel=1.5))

    assert still.horizontal_source == "frame horizontal"
    assert abs(median(still, "body_line_angle")) == pytest.approx(8, abs=1.5)
    assert moving.horizontal_source == "hip path"
    assert median(moving, "body_line_angle") == pytest.approx(0, abs=1.5)


def test_breathing_every_two_strokes():
    report, _, _ = measure(swimmer_xy(times(), breaths_per_cycle=1))

    breaths = report.measures["breaths_per_arm_cycle"]
    assert breaths.experimental
    assert breaths.median() == pytest.approx(1, abs=0.2)
    assert median(report, "breaths_per_min") == pytest.approx(50, abs=10)
    assert len(report.measures["breath_timing"].values) >= 2


def test_no_breaths_and_rotation_say_why():
    report, pose, _ = measure(swimmer_xy(times()))
    summary = report.to_dict(pose)["measures"]
    assert summary["breath_timing"]["status"]
    assert summary["body_rotation"]["status"] == "needs an overhead or front clip"
    assert summary["body_rotation"]["n"] == 0


def test_sections_balance_and_session():
    report, pose, strokes = measure(swimmer_xy(times()), distance_m=50, time_s=40)

    summary = report.measures["pull_depth"].summary()
    assert set(summary["by_section"]) == {"start", "middle", "end"}
    assert set(summary["by_side"]) == {"left", "right"}
    assert report.balance["cycle_time"]["left_minus_right"] == pytest.approx(0, abs=0.05)
    assert report.session["pace_per_100m_s"] == pytest.approx(80)
    rate = strokes.stroke_rate_per_min
    assert report.session["distance_per_cycle_m"] == pytest.approx(1.25 * 60 / rate, abs=0.01)


def test_untrusted_cycles_give_no_values():
    seq = to_sequence(swimmer_xy(times()))
    seq.keypoints[:, :, 2] = 1.0  # every point below the score cutoff
    pose = clean(seq)
    report = measure_technique(pose, analyze_strokes(pose))
    assert all(not m.values for m in report.measures.values())


def test_near_arm_from_raw_scores():
    seq = to_sequence(swimmer_xy(times()))
    assert near_side(seq) is None  # equal scores: can't tell
    seq.keypoints[:, [6, 8, 10], 2] = 5.0  # right arm scored lower: it's the far one
    assert near_side(seq) == "left"


def test_overall_arm_values_come_from_the_near_arm():
    pose = clean(to_sequence(swimmer_xy(times())))
    strokes = analyze_strokes(pose)
    report = measure_technique(pose, strokes, near_side="left")

    summary = report.measures["pull_depth"].summary()
    assert summary["overall_from"].startswith("left arm")
    assert summary["n"] == len(report.measures["pull_depth"].numbers(side="left"))
    right = [v for v in report.measures["pull_depth"].values if v.side == "right"]
    assert right and all(v.confidence == 0.5 for v in right)
    cycle_time = report.measures["cycle_time"]  # timing isn't affected by the view
    assert cycle_time.prefer_side is None


def test_too_short_to_count_breaths():
    report, _, _ = measure(swimmer_xy(times(50), breaths_per_cycle=1))
    assert "at least" in report.measures["breaths_per_min"].status
    assert not report.measures["breaths_per_min"].values


def test_line_angle_finds_tilted_pool_lines():
    img = np.full((540, 960, 3), 120, dtype=np.uint8)
    slope = np.tan(np.radians(7))
    for y0 in (150, 300, 420):
        cv2.line(img, (20, y0), (940, int(y0 + 920 * slope)), (20, 20, 20), 6)
    assert np.degrees(line_angle(img)) == pytest.approx(7, abs=1)
    assert line_angle(np.full((540, 960, 3), 120, dtype=np.uint8)) is None


def test_key_frames_are_written(tmp_path: Path):
    xy = swimmer_xy(times(), kick_hz=2.5, foot_deg=20)
    video = tmp_path / "swim.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    for _ in range(len(xy)):
        writer.write(np.full((H, W, 3), 90, dtype=np.uint8))
    writer.release()
    report, pose, _ = measure(xy)

    images = render_keyframes(video, pose, report, np.zeros(len(pose)), tmp_path / "keys")

    assert {p.stem for p in images} == set(DRAWINGS)
    assert all(cv2.imread(str(p)).shape[1] == W for p in images)
