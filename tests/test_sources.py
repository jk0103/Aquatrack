import numpy as np
import pytest
import synthetic
from conftest import make_raw_pose

from aquatrack.analysis.pose.sources import (
    LocalModelPoseSource,
    PoseSourceError,
    PrecomputedPoseSource,
    RemoteWorkerPoseSource,
    pose_source_from_env,
    validate_raw_pose,
)
from aquatrack.analysis.video import video_identity
from aquatrack.contracts import ModelConfig, RawPose


@pytest.fixture
def identity(swim_video):
    return video_identity(swim_video)


@pytest.fixture
def source(tmp_path, swim_video, identity):
    src = PrecomputedPoseSource(tmp_path / "poses")
    src.directory.mkdir()
    make_raw_pose(swim_video).save(src.path_for(identity.sha256))
    return src


def code(excinfo) -> str:
    return excinfo.value.code


def test_precomputed_pose_is_found_by_the_video_hash(source, swim_video, identity):
    assert source.path_for(identity.sha256).name == f"{identity.sha256}.rawpose.npz"
    raw = source.get_raw_pose(swim_video, identity, "vid-1")
    assert raw.meta.video.sha256 == identity.sha256 and raw.meta.video_id == "vid-1"
    assert raw.meta.provenance.source == "precomputed"
    assert len(raw) == identity.frame_count


def test_missing_pose_data_is_a_clear_retryable_failure(tmp_path, swim_video, identity):
    with pytest.raises(PoseSourceError) as e:
        PrecomputedPoseSource(tmp_path / "empty").get_raw_pose(swim_video, identity, "v")
    assert code(e) == "pose_data_missing" and e.value.retryable
    assert "/" not in e.value.message  # no file paths in what the swimmer sees


def test_pose_made_from_another_video_is_refused(source, swim_video, identity):
    other = make_raw_pose(swim_video)
    other.meta.video.sha256 = "b" * 64
    other.save(source.path_for(identity.sha256))  # right file name, wrong contents
    with pytest.raises(PoseSourceError) as e:
        source.get_raw_pose(swim_video, identity, "v")
    assert code(e) == "pose_video_mismatch"


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"frame_count": 400}, "pose_video_mismatch"),
        ({"fps": 30.0}, "pose_video_mismatch"),
        ({"width": 1920}, "pose_video_mismatch"),
    ],
)
def test_pose_that_does_not_line_up_with_the_video_is_refused(
    identity, swim_video, change, expected
):
    raw = make_raw_pose(swim_video)
    for name, value in change.items():
        setattr(raw.meta.video, name, value)
    with pytest.raises(PoseSourceError) as e:
        validate_raw_pose(raw, identity)
    assert code(e) == expected


def test_a_couple_of_frames_difference_between_decoders_is_tolerated(identity, swim_video):
    raw = make_raw_pose(swim_video)
    raw.meta.video.frame_count += 2
    validate_raw_pose(raw, identity)


def test_pose_referring_to_frames_beyond_the_video_is_refused(identity, swim_video):
    raw = make_raw_pose(swim_video)
    raw.frame_indices = raw.frame_indices + 100
    with pytest.raises(PoseSourceError) as e:
        validate_raw_pose(raw, identity)
    assert code(e) == "pose_video_mismatch"


def test_legacy_pose_without_a_video_hash_is_refused(tmp_path, swim_video, identity):
    seq = synthetic.to_sequence(synthetic.swimmer_xy(synthetic.times(250)))
    legacy = RawPose.load(seq.save(tmp_path / "clip.wholebody.npz"))
    with pytest.raises(PoseSourceError) as e:
        validate_raw_pose(legacy, identity)
    assert code(e) == "pose_data_unverifiable"


def test_pose_without_model_details_is_refused(identity, swim_video):
    raw = make_raw_pose(swim_video, detector=None)
    with pytest.raises(PoseSourceError) as e:
        validate_raw_pose(raw, identity)
    assert code(e) == "pose_data_invalid"


@pytest.mark.parametrize("content", [b"", b"garbage", b"PK\x03\x04half a zip"])
def test_corrupt_pose_file_is_refused(tmp_path, swim_video, identity, content):
    src = PrecomputedPoseSource(tmp_path)
    src.path_for(identity.sha256).write_bytes(content)
    with pytest.raises(PoseSourceError) as e:
        src.get_raw_pose(swim_video, identity, "v")
    assert code(e) == "pose_data_invalid"


def test_empty_pose_file_is_refused(identity, swim_video):
    raw = make_raw_pose(swim_video, xy=np.empty((0, 133, 2)))
    with pytest.raises(PoseSourceError) as e:
        validate_raw_pose(raw, identity)
    assert code(e) == "pose_data_invalid"


def test_source_is_chosen_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.delenv("AQUATRACK_POSE_SOURCE", raising=False)
    assert isinstance(pose_source_from_env(), PrecomputedPoseSource)
    monkeypatch.setenv("AQUATRACK_PRECOMPUTED_POSE_DIR", str(tmp_path))
    assert pose_source_from_env().directory == tmp_path
    monkeypatch.setenv("AQUATRACK_POSE_SOURCE", "local")
    assert isinstance(pose_source_from_env(), LocalModelPoseSource)
    monkeypatch.setenv("AQUATRACK_POSE_SOURCE", "remote")
    assert isinstance(pose_source_from_env(), RemoteWorkerPoseSource)
    monkeypatch.setenv("AQUATRACK_POSE_SOURCE", "mock")
    with pytest.raises(ValueError):
        pose_source_from_env()


def test_local_source_without_models_fails_cleanly(monkeypatch, tmp_path, swim_video, identity):
    from aquatrack.analysis.pose import rtmw_backend

    monkeypatch.setattr(rtmw_backend, "MODELS_DIR", tmp_path)  # no weights here
    with pytest.raises(PoseSourceError) as e:
        LocalModelPoseSource(ModelConfig()).get_raw_pose(swim_video, identity, "v")
    assert code(e) == "model_missing" and not e.value.retryable
    assert "Nothing is wrong with your video" in e.value.message


def test_remote_source_is_an_interface_only(swim_video, identity):
    with pytest.raises(PoseSourceError) as e:
        RemoteWorkerPoseSource().get_raw_pose(swim_video, identity, "v")
    assert code(e) == "remote_worker_unavailable"


def test_local_source_output_passes_the_same_validation(swim_video, identity, monkeypatch):
    """The local estimator, with fake models, yields a RawPose the shared check accepts."""
    from aquatrack.analysis.pose.rtmw_backend import RtmwEstimator

    class Detector:
        name = "fake-detector"

        def detect(self, frame):
            return np.array([[10.0, 10.0, 100.0, 60.0, 0.8], [120.0, 70.0, 150.0, 95.0, 0.9]])

    class Pose:
        def __call__(self, image, bboxes):
            x1, y1, x2, y2 = bboxes[0]
            k = np.zeros((1, 133, 2))
            k[0, :, 0], k[0, :, 1] = (x1 + x2) / 2, (y1 + y2) / 2
            return k, np.full((1, 133), 6.0)

    source = LocalModelPoseSource(ModelConfig())
    source._estimator = RtmwEstimator(detector=Detector(), pose_model=Pose())
    raw = source.get_raw_pose(swim_video, identity, "vid-9")
    assert raw.meta.provenance.source == "local" and raw.meta.video_id == "vid-9"
    assert raw.meta.detector.name == "fake-detector"
    assert (raw.candidates == 2).all()
    # tracking keeps the first target (largest area x confidence) rather than hopping
    assert np.allclose(raw.boxes, [10, 10, 100, 60])
    assert raw.box_confidence[0] == pytest.approx(0.8)
