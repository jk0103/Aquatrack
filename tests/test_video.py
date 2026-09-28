import pytest

from aquatrack.analysis.video import iter_frames, read_video_info


def test_read_video_info(sample_video):
    info = read_video_info(sample_video)
    assert (info.width, info.height) == (64, 48)
    assert info.fps == pytest.approx(10.0)
    assert info.frame_count == 10
    assert info.duration_s == pytest.approx(1.0)


def test_iter_frames_step(sample_video):
    indexes = [i for i, _ in iter_frames(sample_video, step=3)]
    assert indexes == [0, 3, 6, 9]


def test_unreadable_video(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    with pytest.raises(ValueError):
        read_video_info(bad)
