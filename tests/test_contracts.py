import numpy as np
import pytest
import synthetic
from conftest import make_raw_pose
from pydantic import ValidationError

from aquatrack.contracts import (
    LEGACY_SCHEMA_VERSION,
    SCHEMA_VERSION,
    BoxSource,
    ModelConfig,
    RawPose,
    Selection,
)


def test_model_config_defaults_are_the_selected_baseline():
    c = ModelConfig()
    assert (c.detector_weights, c.detector_imgsz, c.detector_confidence) == (
        "yolo11m.pt",
        640,
        0.15,
    )
    assert c.target_selection == "tracking"
    assert (c.pose_weights, c.pose_input_width, c.pose_input_height) == (
        "rtmw_x_stock.onnx",
        288,
        384,
    )


def test_model_config_reads_overrides_from_the_environment(monkeypatch):
    monkeypatch.setenv("AQUATRACK_DETECTOR_WEIGHTS", "yolo11x.pt")
    monkeypatch.setenv("AQUATRACK_DETECTOR_IMGSZ", "1280")
    c = ModelConfig.from_env()
    assert (c.detector_weights, c.detector_imgsz) == ("yolo11x.pt", 1280)
    with pytest.raises(ValidationError):
        ModelConfig(detector_confidence=1.5)


def test_raw_pose_round_trip_keeps_boxes_and_provenance(tmp_path):
    raw = make_raw_pose()
    raw.box_source[3] = int(BoxSource.CARRIED)
    raw.selection[3] = int(Selection.CARRIED)
    back = RawPose.load(raw.save(tmp_path / "a.rawpose.npz"))
    assert back.meta.schema_version == SCHEMA_VERSION
    assert back.meta.config == ModelConfig()
    assert back.meta.detector.name == "yolo11m.pt"
    assert back.meta.provenance.source == "precomputed"
    assert back.box_source[3] == BoxSource.CARRIED and back.selection[3] == Selection.CARRIED
    np.testing.assert_allclose(back.boxes, raw.boxes, atol=1e-3)
    np.testing.assert_allclose(back.keypoints, raw.keypoints, atol=1e-5)
    np.testing.assert_allclose(back.timestamps_s, raw.timestamps_s)


def test_legacy_student_pose_files_still_load(tmp_path):
    seq = synthetic.to_sequence(synthetic.swimmer_xy(synthetic.times(40)))
    raw = RawPose.load(seq.save(tmp_path / "clip.wholebody.npz"))
    assert raw.meta.schema_version == LEGACY_SCHEMA_VERSION
    assert raw.meta.provenance.source == "legacy"
    assert raw.meta.video is None and not raw.has_boxes
    assert (raw.selection == Selection.UNKNOWN).all()
    np.testing.assert_allclose(raw.keypoints, seq.keypoints, atol=1e-5)
    # and a re-saved legacy file stays readable
    assert len(RawPose.load(raw.save(tmp_path / "again.npz"))) == 40


def test_raw_pose_rejects_wrong_shapes():
    raw = make_raw_pose()
    with pytest.raises(ValidationError):
        RawPose(**{**dict(raw), "boxes": raw.boxes[:-1]})
    with pytest.raises(ValidationError):
        RawPose(**{**dict(raw), "keypoints": raw.keypoints[:, :17]})


@pytest.mark.parametrize("content", [b"", b"not a zip file", b"PK\x03\x04broken"])
def test_unreadable_pose_files_raise_value_error(tmp_path, content):
    path = tmp_path / "bad.rawpose.npz"
    path.write_bytes(content)
    with pytest.raises(ValueError):
        RawPose.load(path)


def test_pose_file_from_a_newer_schema_is_refused(tmp_path):
    raw = make_raw_pose()
    raw.meta.schema_version = "2.0"
    with pytest.raises(ValueError, match="unsupported RawPose schema"):
        RawPose.load(raw.save(tmp_path / "new.npz"))


def test_other_npz_files_are_not_pose_files(tmp_path):
    np.savez(tmp_path / "other.npz", something=np.arange(3))
    with pytest.raises(ValueError, match="not a pose file"):
        RawPose.load(tmp_path / "other.npz")
