"""The restricted security rules (firebase/restricted/), checked against the emulators.

Skipped unless the emulators are up. The test loads the restricted rules into the running
emulators, runs, and puts back whatever was loaded before (the normal rules, or the
restricted ones when the emulators were started with `--restricted`). Requests go through
the same REST endpoints the web app's SDK uses.

An "invited" account carries the custom claim the backend sets for listed accounts; a
"stranger" is signed in with a valid token but has no claim, which is what any account
created without an invitation would be.
"""

import json
import secrets
import urllib.parse
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "demo-aquatrack"
BUCKET = f"{PROJECT}.appspot.com"
AUTH = "http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1"
DOCS = f"http://127.0.0.1:8080/v1/projects/{PROJECT}/databases/(default)/documents"
STORAGE = f"http://127.0.0.1:9199/v0/b/{BUCKET}/o"
FIRESTORE_RULES = f"http://127.0.0.1:8080/emulator/v1/projects/{PROJECT}:securityRules"
STORAGE_RULES = "http://127.0.0.1:9199/internal/setRules"
ADMIN = {"Authorization": "Bearer owner"}
CLAIM = "aquatrack_demo"


def _emulators_running() -> bool:
    try:
        httpx.get("http://127.0.0.1:9199/", timeout=1)  # any answer: the storage emulator is up
        return all(
            httpx.get(url, timeout=1).status_code < 500
            for url in ("http://127.0.0.1:9099/", "http://127.0.0.1:8080/")
        )
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not _emulators_running(), reason="Firebase emulators not running")


def load_rules(folder: str) -> None:
    firestore = (ROOT / folder / "firestore.rules").read_text()
    storage = (ROOT / folder / "storage.rules").read_text()
    res = httpx.put(FIRESTORE_RULES, json={"rules": {"files": [{"content": firestore}]}})
    assert res.status_code == 200, res.text
    res = httpx.put(
        STORAGE_RULES, json={"rules": {"files": [{"name": "storage.rules", "content": storage}]}}
    )
    assert res.status_code == 200, res.text


def rules_in_force() -> str:
    """Which rule set the emulators have loaded: a signed-in account without the claim can
    look for its own (missing) profile under the normal rules only."""
    probe = Account()
    res = httpx.get(f"{DOCS}/profiles/{probe.uid}", headers=probe.firestore)
    return "firebase" if res.status_code == 404 else "firebase/restricted"


@pytest.fixture(scope="module", autouse=True)
def restricted_rules():
    before = rules_in_force()
    load_rules("firebase/restricted")
    assert rules_in_force() == "firebase/restricted"
    yield
    load_rules(before)


class Account:
    def __init__(self, invited: bool = False):
        self.email = f"restricted-{secrets.token_hex(6)}@example.test"
        self.password = secrets.token_urlsafe(12)
        res = httpx.post(
            f"{AUTH}/accounts:signUp?key=demo-key",
            json={"email": self.email, "password": self.password, "returnSecureToken": True},
        ).json()
        self.uid, token = res["localId"], res["idToken"]
        if invited:
            # What the backend does for a listed account (firebase.sync_access_claims).
            res = httpx.post(
                f"{AUTH}/accounts:update",
                headers=ADMIN,
                json={"localId": self.uid, "customAttributes": json.dumps({CLAIM: True})},
            )
            assert res.status_code == 200, res.text
            token = httpx.post(
                f"{AUTH}/accounts:signInWithPassword?key=demo-key",
                json={"email": self.email, "password": self.password, "returnSecureToken": True},
            ).json()["idToken"]
        self.firestore = {"Authorization": f"Bearer {token}"}
        self.storage = {"Authorization": f"Firebase {token}"}


@pytest.fixture(scope="module")
def invited():
    return Account(invited=True)


@pytest.fixture(scope="module")
def other_invited():
    return Account(invited=True)


@pytest.fixture(scope="module")
def stranger():
    return Account()


def video_fields(uid: str, video_id: str) -> dict:
    return {
        "fields": {
            "uid": {"stringValue": uid},
            "status": {"stringValue": "uploaded"},
            "storagePath": {"stringValue": f"videos/{uid}/{video_id}.webm"},
        }
    }


def create_video(account: Account, video_id: str) -> httpx.Response:
    """Create a video document the way the web app does (createdAt = server time)."""
    name = f"projects/{PROJECT}/databases/(default)/documents/videos/{video_id}"
    return httpx.post(
        f"{DOCS}:commit",
        headers=account.firestore,
        json={
            "writes": [
                {
                    "update": {"name": name, **video_fields(account.uid, video_id)},
                    "updateTransforms": [
                        {"fieldPath": "createdAt", "setToServerValue": "REQUEST_TIME"}
                    ],
                    "currentDocument": {"exists": False},
                }
            ]
        },
    )


def upload(account: Account, uid: str, name: str) -> httpx.Response:
    path = urllib.parse.quote(f"videos/{uid}/{name}", safe="")
    return httpx.post(
        f"{STORAGE}?name={path}",
        headers={**account.storage, "Content-Type": "video/webm"},
        content=b"not really a video",
    )


def download(account: Account, uid: str, name: str) -> httpx.Response:
    path = urllib.parse.quote(f"videos/{uid}/{name}", safe="")
    return httpx.get(f"{STORAGE}/{path}?alt=media", headers=account.storage)


def test_an_invited_account_can_use_its_own_data(invited):
    video_id = f"v-{secrets.token_hex(4)}"
    assert create_video(invited, video_id).status_code == 200
    assert httpx.get(f"{DOCS}/videos/{video_id}", headers=invited.firestore).status_code == 200
    assert upload(invited, invited.uid, f"{video_id}.webm").status_code == 200
    assert download(invited, invited.uid, f"{video_id}.webm").status_code == 200


def test_a_signed_in_stranger_can_do_nothing_in_firestore(invited, stranger):
    theirs = f"v-{secrets.token_hex(4)}"
    assert create_video(invited, theirs).status_code == 200
    # not even documents that would be the stranger's own
    assert create_video(stranger, f"v-{secrets.token_hex(4)}").status_code == 403
    assert (
        httpx.get(f"{DOCS}/profiles/{stranger.uid}", headers=stranger.firestore).status_code == 403
    )
    assert httpx.get(f"{DOCS}/videos/{theirs}", headers=stranger.firestore).status_code == 403
    for collection in ("training_plans", "training_sessions", "account_deletions"):
        res = httpx.get(f"{DOCS}/{collection}/anything", headers=stranger.firestore)
        assert res.status_code == 403, collection


def test_a_signed_in_stranger_can_do_nothing_in_storage(invited, stranger):
    name = f"{secrets.token_hex(4)}.webm"
    assert upload(invited, invited.uid, name).status_code == 200
    assert upload(stranger, stranger.uid, name).status_code == 403  # their own folder
    assert download(stranger, invited.uid, name).status_code == 403
    path = urllib.parse.quote("demo_fixtures/pose/anything.rawpose.npz", safe="")
    assert httpx.get(f"{STORAGE}/{path}?alt=media", headers=stranger.storage).status_code == 403


def test_nobody_reads_the_saved_pose_files_or_writes_results(invited):
    path = urllib.parse.quote("demo_fixtures/pose/anything.rawpose.npz", safe="")
    assert httpx.get(f"{STORAGE}/{path}?alt=media", headers=invited.storage).status_code == 403
    res = httpx.post(
        f"{STORAGE}?name={path}",
        headers={**invited.storage, "Content-Type": "application/octet-stream"},
        content=b"x",
    )
    assert res.status_code == 403
    video_id = f"v-{secrets.token_hex(4)}"
    assert create_video(invited, video_id).status_code == 200
    res = httpx.patch(
        f"{DOCS}/videos/{video_id}?updateMask.fieldPaths=status",
        headers=invited.firestore,
        json={"fields": {"status": {"stringValue": "ready"}}},
    )
    assert res.status_code == 403  # clients can never forge a job state or a result


def test_invited_accounts_still_cannot_see_each_other(invited, other_invited):
    video_id = f"v-{secrets.token_hex(4)}"
    name = f"{video_id}.webm"
    assert create_video(invited, video_id).status_code == 200
    assert upload(invited, invited.uid, name).status_code == 200
    assert (
        httpx.get(f"{DOCS}/videos/{video_id}", headers=other_invited.firestore).status_code == 403
    )
    assert download(other_invited, invited.uid, name).status_code == 403
    assert upload(other_invited, invited.uid, "intruder.webm").status_code == 403


def test_without_a_login_nothing_is_readable():
    assert httpx.get(f"{DOCS}/videos/anything").status_code == 403
    path = urllib.parse.quote("videos/someone/a.webm", safe="")
    assert httpx.get(f"{STORAGE}/{path}?alt=media").status_code in (401, 403)
