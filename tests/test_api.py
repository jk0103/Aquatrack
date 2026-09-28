import pytest
from fastapi.testclient import TestClient

from aquatrack.api import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path / "uploads")
    return TestClient(main.app)


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_upload_video(client, sample_video):
    with sample_video.open("rb") as f:
        res = client.post("/videos", files={"file": ("swim.mp4", f, "video/mp4")})
    assert res.status_code == 200
    body = res.json()
    assert body["frame_count"] == 10
    assert body["duration_s"] == pytest.approx(1.0)


def test_upload_rejects_non_video(client):
    res = client.post("/videos", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert res.status_code == 400


def test_upload_rejects_corrupt_video(client, tmp_path):
    res = client.post("/videos", files={"file": ("swim.mp4", b"garbage", "video/mp4")})
    assert res.status_code == 400
    assert not any((tmp_path / "uploads").iterdir())
