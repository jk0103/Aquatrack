import pytest
from conftest import make_raw_pose
from fastapi.testclient import TestClient
from firebase_admin import auth

from aquatrack.analysis.pose.sources import PrecomputedPoseSource
from aquatrack.analysis.video import video_identity
from aquatrack.api import firebase, main
from aquatrack.api.jobs import InlineRunner
from aquatrack.api.store import MemoryStore

UID = "swimmer-1"
GOOD = {"Authorization": "Bearer good-token"}
OTHER = {"Authorization": "Bearer other-token"}


@pytest.fixture
def store(swim_video):
    s = MemoryStore()
    path = f"videos/{UID}/vid1.mp4"
    s.files[path] = swim_video.read_bytes()
    s.videos["vid1"] = {
        "uid": UID,
        "storagePath": path,
        "status": "uploaded",
        "contentType": "video/mp4",
        "sizeBytes": len(s.files[path]),
        "stroke": "Freestyle",
        "camera": "Underwater",
    }
    return s


@pytest.fixture
def client(monkeypatch, store, tmp_path, swim_video):
    def fake_verify(token: str) -> dict:
        if token == "good-token":
            return {"uid": UID, "email": "alice@example.com"}
        if token == "other-token":
            return {"uid": "swimmer-2"}
        raise auth.InvalidIdTokenError("bad token")

    monkeypatch.setattr(firebase, "verify_token", fake_verify)
    source = PrecomputedPoseSource(tmp_path / "poses")
    source.directory.mkdir()
    make_raw_pose(swim_video).save(source.path_for(video_identity(swim_video).sha256))
    main.app.dependency_overrides[main.get_runner] = lambda: InlineRunner(store, source)
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_the_old_unauthenticated_upload_endpoint_is_gone(client, sample_video):
    """POST /videos used to accept any file from anyone. Uploads go to Firebase Storage."""
    with sample_video.open("rb") as f:
        res = client.post("/videos", files={"file": ("swim.mp4", f, "video/mp4")})
    assert res.status_code in (404, 405)
    assert all(r.path != "/videos" for r in main.app.routes)


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer bad-token"}, {"Authorization": "Basic good-token"}],
)
def test_analyze_requires_a_valid_login(client, store, headers):
    assert client.post("/videos/vid1/analyze", headers=headers).status_code == 401
    assert store.videos["vid1"]["status"] == "uploaded"


def test_analyze_own_video_runs_and_stores_results(client, store):
    res = client.post("/videos/vid1/analyze", headers=GOOD)
    assert res.status_code == 202
    assert res.json() == {"id": "vid1", "status": "queued", "started": True, "attempts": 1}
    assert store.videos["vid1"]["status"] == "ready"
    assert store.videos["vid1"]["analysisSummary"]["cyclesPerMin"] == 50.0


def test_analyze_twice_does_not_rerun(client, store):
    client.post("/videos/vid1/analyze", headers=GOOD)
    first_id = store.videos["vid1"]["latestAnalysisId"]
    res = client.post("/videos/vid1/analyze", headers=GOOD)
    assert res.status_code == 202 and res.json()["started"] is False
    assert res.json()["status"] == "ready"
    assert store.videos["vid1"]["latestAnalysisId"] == first_id


def test_cannot_analyze_someone_elses_video(client, store):
    res = client.post("/videos/vid1/analyze", headers=OTHER)
    assert res.status_code == 404
    assert store.videos["vid1"]["status"] == "uploaded" and not store.analyses


def test_unknown_video_is_404(client):
    assert client.post("/videos/missing/analyze", headers=GOOD).status_code == 404


def test_retry_limit_is_reported_as_conflict(client, store):
    store.videos["vid1"].update(status="failed", job={"attempts": 3})
    assert client.post("/videos/vid1/analyze", headers=GOOD).status_code == 409


def test_error_responses_do_not_leak_paths(client, store):
    store.videos["vid1"]["storagePath"] = "videos/someone-else/secret.mp4"
    res = client.post("/videos/vid1/analyze", headers=GOOD)
    assert res.status_code == 422 and "secret" not in res.text


def test_interpret_again_is_for_the_owner_of_a_finished_analysis(client, store):
    assert client.post("/videos/vid1/interpret", headers=GOOD).status_code == 409  # nothing yet
    assert client.post("/videos/vid1/analyze", headers=GOOD).status_code == 202
    assert len(store.interpretations) == 1
    res = client.post("/videos/vid1/interpret", headers=GOOD)
    assert res.status_code == 201 and len(store.interpretations) == 2
    body = res.json()
    assert body["baseline"] is True and body["priorities"] == 0 and body["observations"] > 0
    assert client.post("/videos/vid1/interpret").status_code == 401
    assert client.post("/videos/vid1/interpret", headers=OTHER).status_code == 404
    assert len(store.interpretations) == 2


def test_delete_compare_and_progress_need_a_login_and_ownership(client, store):
    assert client.post("/videos/vid1/analyze", headers=GOOD).status_code == 202
    for method, path in (
        ("delete", "/videos/vid1"),
        ("get", "/videos/vid1/compare/vid1"),
        ("get", "/progress"),
    ):
        assert getattr(client, method)(path).status_code == 401
    assert client.delete("/videos/vid1", headers=OTHER).status_code == 404
    assert client.get("/videos/vid1/compare/other", headers=GOOD).status_code == 404
    mine = client.get("/progress", headers=GOOD).json()
    assert mine["progress"]["analyzed"] == 1 and mine["progress"]["baseline"] is True
    assert client.get("/progress", headers=OTHER).json()["progress"]["analyzed"] == 0
    assert client.delete("/videos/vid1", headers=GOOD).json() == {
        "deleted": True,
        "already_deleted": False,
    }
    assert "vid1" not in store.videos and store.analyses == {} and store.feedback == {}
    assert client.delete("/videos/vid1", headers=GOOD).json()["already_deleted"] is True
    assert client.post("/videos/vid1/analyze", headers=GOOD).status_code == 404
