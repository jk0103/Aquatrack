"""Security rules, checked against the running Firebase emulators.

Skipped unless the emulators are up (`npm --prefix frontend run emulators`). These go
through the same REST endpoints the web app's SDK uses, so the rules really are applied;
"admin" requests use the emulator's owner token the way the backend does.
"""

import secrets
import urllib.parse

import httpx
import pytest

PROJECT = "demo-aquatrack"
BUCKET = f"{PROJECT}.appspot.com"
AUTH = "http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1"
DOCS = f"http://127.0.0.1:8080/v1/projects/{PROJECT}/databases/(default)/documents"
STORAGE = f"http://127.0.0.1:9199/v0/b/{BUCKET}/o"
ADMIN = {"Authorization": "Bearer owner"}


def _emulators_running() -> bool:
    try:
        return all(
            httpx.get(url, timeout=1).status_code < 500
            for url in ("http://127.0.0.1:9099/", "http://127.0.0.1:8080/")
        )
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not _emulators_running(), reason="Firebase emulators not running")


class User:
    def __init__(self):
        res = httpx.post(
            f"{AUTH}/accounts:signUp?key=demo-key",
            json={
                "email": f"rules-{secrets.token_hex(6)}@example.test",
                "password": secrets.token_urlsafe(12),
                "returnSecureToken": True,
            },
        ).json()
        self.uid, self.token = res["localId"], res["idToken"]
        self.firestore = {"Authorization": f"Bearer {self.token}"}
        self.storage = {"Authorization": f"Firebase {self.token}"}


@pytest.fixture(scope="module")
def alice():
    return User()


@pytest.fixture(scope="module")
def bob():
    return User()


def fields(**values):
    out = {}
    for key, value in values.items():
        kind = "integerValue" if isinstance(value, int) else "stringValue"
        out[key] = {kind: str(value) if isinstance(value, int) else value}
    return out


def create_video(user: User, video_id: str, **overrides) -> httpx.Response:
    """Create a video record the way the web app does (createdAt = server time)."""
    data = {
        "uid": user.uid,
        "status": "uploaded",
        "storagePath": f"videos/{user.uid}/{video_id}.mp4",
        "fileName": "swim.mp4",
        "contentType": "video/mp4",
        "sizeBytes": 1234,
    } | overrides
    name = f"projects/{PROJECT}/databases/(default)/documents/videos/{video_id}"
    write = {
        "update": {"name": name, "fields": fields(**data)},
        "updateTransforms": [{"fieldPath": "createdAt", "setToServerValue": "REQUEST_TIME"}],
        "currentDocument": {"exists": False},
    }
    return httpx.post(f"{DOCS}:commit", json={"writes": [write]}, headers=user.firestore)


@pytest.fixture(scope="module")
def video(alice):
    """Alice's video, with an analysis and an artifact written by the backend (admin)."""
    video_id = f"rules-{secrets.token_hex(6)}"
    assert create_video(alice, video_id).status_code == 200
    analysis = f"{DOCS}/videos/{video_id}/analyses/a1"
    body = {"fields": fields(uid=alice.uid, schema_version="1.0")}
    assert httpx.patch(analysis, json=body, headers=ADMIN).status_code == 200
    artifact = f"analysis/{alice.uid}/{video_id}/a1/raw_pose.npz"
    up = httpx.post(
        f"http://127.0.0.1:9199/upload/storage/v1/b/{BUCKET}/o",
        params={"uploadType": "media", "name": artifact},
        content=b"pose-bytes",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert up.status_code == 200
    return {"id": video_id, "analysis": analysis, "artifact": artifact}


def obj(path: str) -> str:
    return f"{STORAGE}/{urllib.parse.quote(path, safe='')}"


def upload(user: User, path: str, content_type: str = "video/mp4") -> int:
    headers = user.storage | {"Content-Type": content_type}
    return httpx.post(
        STORAGE, params={"name": path}, content=b"x" * 64, headers=headers
    ).status_code


# ---------- existing upload flow ----------


def test_owner_can_upload_a_video_and_watch_it(alice):
    path = f"videos/{alice.uid}/{secrets.token_hex(4)}.mp4"
    assert upload(alice, path) == 200
    assert httpx.get(obj(path), params={"alt": "media"}, headers=alice.storage).status_code == 200


def test_upload_must_be_a_video_in_your_own_folder(alice, bob):
    assert upload(alice, f"videos/{bob.uid}/steal.mp4") == 403
    assert upload(alice, f"videos/{alice.uid}/notes.txt", content_type="text/plain") == 403
    assert httpx.post(STORAGE, params={"name": "videos/x/y.mp4"}, content=b"x").status_code == 403


def test_others_cannot_watch_a_video(alice, bob):
    path = f"videos/{alice.uid}/{secrets.token_hex(4)}.mp4"
    assert upload(alice, path) == 200
    assert httpx.get(obj(path), params={"alt": "media"}, headers=bob.storage).status_code == 403
    assert httpx.get(obj(path), params={"alt": "media"}).status_code == 403


# ---------- video records and job state ----------


def test_video_record_is_private_to_its_owner(alice, bob, video):
    url = f"{DOCS}/videos/{video['id']}"
    assert httpx.get(url, headers=alice.firestore).status_code == 200
    assert httpx.get(url, headers=bob.firestore).status_code == 403
    assert httpx.get(url).status_code == 403


def test_clients_cannot_forge_or_change_job_state(alice, bob, video):
    # can't create a record that already claims to be analysed, or one owned by someone else
    assert create_video(alice, f"forge-{secrets.token_hex(4)}", status="ready").status_code == 403
    assert create_video(alice, f"forge-{secrets.token_hex(4)}", uid=bob.uid).status_code == 403
    url = f"{DOCS}/videos/{video['id']}"
    for field, value in (("status", "ready"), ("latestAnalysisId", "fake")):
        res = httpx.patch(
            url,
            params={"updateMask.fieldPaths": field},
            json={"fields": fields(**{field: value})},
            headers=alice.firestore,
        )
        assert res.status_code == 403
    assert httpx.delete(url, headers=alice.firestore).status_code == 403


# ---------- analysis results ----------


def test_owner_can_read_their_analysis(alice, video):
    res = httpx.get(video["analysis"], headers=alice.firestore)
    assert res.status_code == 200
    assert res.json()["fields"]["schema_version"]["stringValue"] == "1.0"


def test_others_cannot_read_an_analysis(bob, video):
    assert httpx.get(video["analysis"], headers=bob.firestore).status_code == 403
    assert httpx.get(video["analysis"]).status_code == 403


def test_clients_cannot_write_analysis_results(alice, video):
    forged = {"fields": fields(uid=alice.uid, schema_version="1.0", grade="good")}
    assert httpx.patch(video["analysis"], json=forged, headers=alice.firestore).status_code == 403
    other = f"{DOCS}/videos/{video['id']}/analyses/forged"
    assert httpx.patch(other, json=forged, headers=alice.firestore).status_code == 403
    assert httpx.delete(video["analysis"], headers=alice.firestore).status_code == 403


# ---------- analysis artifacts in storage ----------


def test_artifacts_are_readable_only_by_their_owner(alice, bob, video):
    url = obj(video["artifact"])
    assert httpx.get(url, params={"alt": "media"}, headers=alice.storage).content == b"pose-bytes"
    assert httpx.get(url, params={"alt": "media"}, headers=bob.storage).status_code == 403
    assert httpx.get(url, params={"alt": "media"}).status_code == 403


def test_clients_cannot_write_artifacts(alice, video):
    path = f"analysis/{alice.uid}/{video['id']}/a1/forged.npz"
    assert upload(alice, path, content_type="application/octet-stream") == 403
    assert httpx.delete(obj(video["artifact"]), headers=alice.storage).status_code == 403
