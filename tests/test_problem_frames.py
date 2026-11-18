"""Problem frames: which still frames may illustrate the feedback's priorities.

Feedback comes from the synthetic swimmer (test_interpretation / test_feedback); the pose
is a hand-made PoseView so trust can be switched off frame by frame. Nothing here is a
real video or real inference.
"""

import numpy as np
from conftest import make_raw_pose
from test_biomechanics import FREESTYLE, VIDEO, side_view
from test_feedback import feedback
from test_interpretation import EVEN, UNEVEN, result

from aquatrack.analysis import problem_frames as pf
from aquatrack.analysis.pipeline import analyze
from aquatrack.api.store import MemoryStore, VideoRecord
from aquatrack.contracts import MetricSample, ProblemFrames

FPS = 25.0
GOAL = ("stroke_consistency",)  # a goal the rhythm rule matches, so it is ranked


def view(seconds=12.0, camera="right", timing="right") -> pf.PoseView:
    n = int(seconds * FPS)
    xy = np.full((n, 133, 2), np.nan)
    joints = pf.JOINTS["right"]
    for k, (x, y) in {
        "shoulder": (0.55, 0.40),
        "elbow": (0.50, 0.55),
        "wrist": (0.45, 0.70),
    }.items():
        xy[:, joints[k]] = (x, y)
    left = pf.JOINTS["left"]
    for k in left:
        xy[:, left[k]] = (0.5, 0.45)
    return pf.PoseView(
        timestamps_s=np.arange(n) / FPS,
        frame_indices=np.arange(n),
        xy=xy,
        confidence=np.full((n, 133), 0.9),
        observed=np.isfinite(xy[..., 0]),
        supported={"right": np.ones(n, bool), "left": np.zeros(n, bool)},
        camera_arm=camera,
        timing_arm=timing,
        width=1920,
        height=1080,
    )


def ranked(times=UNEVEN):
    f = feedback(times, goals=GOAL)
    assert [i.category for i in f.items].count("priority") == 1
    return f, result(times)


def odd_samples(f):
    item = next(i for i in f.items if i.category == "priority")
    return [s for e in item.evidence if e.metric_key == "cycle_duration" for s in e.samples]


def frame_of(t_s: float) -> int:
    return int(round(t_s * FPS))


# ---------- only what the advice reported ----------


def test_no_priority_means_no_frames_and_says_why():
    for f in (feedback(EVEN, goals=GOAL), feedback(EVEN)):
        out = pf.select_frames(f, result(EVEN), view())
        assert out.frames == [] and out.empty_reason == "no_issue"


def test_an_unranked_focus_is_not_shown_as_a_fix():
    f = feedback(UNEVEN)  # an issue, but no goal or earlier swim makes it a priority
    assert any(i.category == "focus" for i in f.items)
    out = pf.select_frames(f, result(UNEVEN), view())
    assert out.frames == [] and out.empty_reason == "no_issue"


def test_frames_are_the_priority_evidence_moments_and_nothing_else():
    f, r = ranked()
    samples = odd_samples(f)
    out = pf.select_frames(f, r, view())
    assert 1 <= len(out.frames) <= len(samples)
    item = next(i for i in f.items if i.category == "priority")
    assert {fr.item_id for fr in out.frames} == {item.id}
    assert {fr.t_s for fr in out.frames} == {s.t_s for s in samples}
    # One frame per cycle, and cycle numbers point into the analysis's own cycles.
    assert len({fr.cycle_index for fr in out.frames}) == len(out.frames)
    duration = next(m for m in r.metrics if m.key == "cycle_duration")
    for fr in out.frames:
        assert duration.samples[fr.cycle_index - 1].t_s == fr.t_s


def test_a_priority_with_no_moments_in_the_video_gets_no_frames():
    f, r = ranked()
    item = next(i for i in f.items if i.category == "priority")
    item.finding_id = "issue.history.rhythm_less_steady"  # evidence is one number, no cycles
    out = pf.select_frames(f, r, view())
    assert out.frames == [] and out.empty_reason == "no_frame_rule"


# ---------- at most five, spread over cycles ----------


def test_never_more_than_five_frames_and_never_two_from_one_cycle():
    f, r = ranked()
    item = next(i for i in f.items if i.category == "priority")
    evidence = next(e for e in item.evidence if e.metric_key == "cycle_duration")
    many = [
        MetricSample(
            t_s=0.5 + k, value=1.2 + (0.3 if k % 2 else -0.25), start_s=0.5 + k, end_s=1.5 + k
        )
        for k in range(9)
    ]
    evidence.samples = [*many, many[0].model_copy()]  # the same cycle listed twice
    out = pf.select_frames(f, r, view())
    assert len(out.frames) == pf.MAX_FRAMES == 5
    assert len({(fr.cycle_start_s, fr.cycle_end_s) for fr in out.frames}) == 5
    # The cycles furthest from the usual time come first: all four +0.3 s ones, then one more.
    assert sum(fr.arrows[0].label.startswith("Longer") for fr in out.frames) == 4


# ---------- only trusted frames ----------


def test_untrusted_moments_are_skipped_or_moved_to_a_neighbouring_trusted_frame():
    f, r = ranked()
    first, second, third = odd_samples(f)
    v = view()
    i = frame_of(first.t_s)
    v.supported["right"][i - 2 : i + 3] = False  # no supported frame anywhere near
    j = frame_of(second.t_s)
    v.confidence[j, pf.JOINTS["right"]["wrist"]] = 0.2  # this frame's wrist is unsure...
    out = pf.select_frames(f, r, v)
    times = sorted(fr.t_s for fr in out.frames)
    assert first.t_s not in times
    assert round((j + 1) / FPS, 3) in times  # ...so the next frame of that cycle stands in
    assert third.t_s in times


def test_far_arm_filled_in_or_cut_off_points_are_never_used():
    f, r = ranked()
    out = pf.select_frames(f, r, view(camera="left"))  # cycles timed on the hidden arm
    assert out.frames == [] and out.empty_reason == "no_trusted_frame"

    v = view()
    v.observed[:, pf.JOINTS["right"]["elbow"]] = False  # interpolated, not the model's own
    assert pf.select_frames(f, r, v).empty_reason == "no_trusted_frame"

    v = view()
    v.xy[:, pf.JOINTS["right"]["wrist"]] = (0.45, 0.995)  # at the bottom edge of the picture
    assert pf.select_frames(f, r, v).frames == []

    v = view()
    v.supported["right"][:] = False  # recovery / behind the body: never followed
    assert pf.select_frames(f, r, v).frames == []


def test_blurry_frames_are_left_out():
    f, r = ranked()
    first = odd_samples(f)[0]
    blurry = set(range(frame_of(first.t_s) - 2, frame_of(first.t_s) + 3))
    out = pf.select_frames(f, r, view(), sharpness=lambda i: 5.0 if i in blurry else 120.0)
    assert first.t_s not in {fr.t_s for fr in out.frames} and out.frames
    assert all(fr.sharpness == 120.0 for fr in out.frames)


# ---------- arrows ----------


def test_arrows_point_at_that_frames_own_wrist_with_a_short_label():
    f, r = ranked()
    v = view()
    s = odd_samples(f)[0]
    i = frame_of(s.t_s)
    v.xy[i, pf.JOINTS["right"]["wrist"]] = (0.31, 0.77)  # the hand somewhere else in this frame
    fr = next(x for x in pf.select_frames(f, r, v).frames if x.t_s == s.t_s)
    (arrow,) = fr.arrows
    assert arrow.joint == "right wrist" and arrow.to == (0.31, 0.77)
    assert len(arrow.label.split()) <= pf.MAX_LABEL_WORDS
    assert f"{s.value:.2f} s" in arrow.label  # the measured cycle time, nothing else
    assert 0 < arrow.label_at[0] < 1 and 0 < arrow.label_at[1] < 1


# ---------- pose, video and storage ----------


def test_pose_view_reads_the_analysis_own_trust_from_raw_pose():
    raw = make_raw_pose(xy=side_view(far="left"))
    res, _ = analyze(raw, "v", FREESTYLE, VIDEO)
    v = pf.pose_view(raw, res)
    assert v.camera_arm == res.coverage.camera_side.arm == "right"
    assert v.xy.shape == (len(raw.frame_indices), 133, 2)
    assert v.supported["right"].any()
    finite = v.xy[np.isfinite(v.xy)]
    assert finite.min() >= 0 and finite.max() <= 1  # 0-1 of the picture


def test_frames_are_read_from_the_video_as_jpegs(sample_video):
    v = view(seconds=1.0)
    v.frame_indices = np.minimum(v.frame_indices, 9)
    reader = pf.FrameReader(sample_video, v)
    try:
        data, w, h = reader.jpeg(3)
        assert data[:2] == b"\xff\xd8" and (w, h) == (64, 48)
        assert reader.sharpness(3) is not None
        assert reader.jpeg(500) is None  # past the end of the clip
    finally:
        reader.close()


def test_frames_are_stored_with_the_analysis_and_deleted_with_the_video(tmp_path):
    store = MemoryStore()
    video = VideoRecord(id="v1", uid="u1", storage_path="videos/u1/v1.mp4", status="ready")
    store.videos["v1"] = {"uid": "u1", "storagePath": video.storage_path, "status": "ready"}
    f, r = ranked()
    chosen = pf.select_frames(f, r, view())
    image = tmp_path / "1.jpg"
    image.write_bytes(b"\xff\xd8jpeg")
    chosen.frames = [chosen.frames[0].model_copy(update={"image": "1.jpg"})]
    doc = store.save_problem_frames(video, "a1", "fb1", chosen.to_firestore(), {"1.jpg": image})
    path = "analysis/u1/v1/a1/frames/fb1/1.jpg"
    assert doc["frames"][0]["image"] == path and store.files[path] == b"\xff\xd8jpeg"
    assert doc["uid"] == "u1"
    assert ProblemFrames.model_validate(store.get_problem_frames("v1", "fb1")).frames
    store.delete_video_data(video)
    assert store.get_problem_frames("v1", "fb1") is None and path not in store.files
