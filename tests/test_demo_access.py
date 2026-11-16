"""The account-restricted demonstration: who gets in, and where saved pose data may be used.

Unit tests with fakes (no Firebase, no models). The security rules themselves are checked
against the emulators in tests/test_emulator_restricted_rules.py.
"""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import make_raw_pose
from fastapi.testclient import TestClient
from firebase_admin import auth

from aquatrack.analysis.pose.sources import (
    DEMO_UNSUPPORTED,
    PoseSourceError,
    PrecomputedPoseSource,
)
from aquatrack.analysis.video import video_identity
from aquatrack.api import config, demo, firebase, main
from aquatrack.api.jobs import InlineRunner
from aquatrack.api.store import MemoryStore

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {"Authorization": "Bearer allowed-token"}
STRANGER = {"Authorization": "Bearer stranger-token"}
STAGING = {
    "AQUATRACK_ENV": "staging",
    "FIREBASE_PROJECT_ID": "aquatrack-school-demo",
    "AQUATRACK_ALLOW_PRODUCTION_FIREBASE": "1",
}
DEMO = {
    **STAGING,
    "AQUATRACK_DEMO": "1",
    "AQUATRACK_ACCESS": "restricted",
    "AQUATRACK_ALLOWED_UIDS": "uid-allowed",
    "AQUATRACK_POSE_SOURCE": "precomputed",
}
NAMES = [
    *DEMO,
    "AQUATRACK_WORKER",
    "FIREBASE_AUTH_EMULATOR_HOST",
    "FIRESTORE_EMULATOR_HOST",
    "STORAGE_EMULATOR_HOST",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "AQUATRACK_LLM_PROVIDER",
]


def env(monkeypatch, **values):
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)
    for name, value in values.items():
        monkeypatch.setenv(name, value)


# --- who is allowed ------------------------------------------------------------------------


def test_access_is_open_unless_restricted_and_a_typo_closes_it(monkeypatch):
    env(monkeypatch)
    assert config.is_allowed("anyone")
    env(monkeypatch, AQUATRACK_ACCESS="restricted", AQUATRACK_ALLOWED_UIDS="a, b\nc")
    assert config.allowed_uids() == {"a", "b", "c"}
    assert config.is_allowed("b") and not config.is_allowed("anyone")
    env(monkeypatch, AQUATRACK_ACCESS="restrcted")  # misspelt: nobody gets in
    assert not config.is_allowed("anyone")
    assert any("AQUATRACK_ACCESS" in p for p in config.validate())


@pytest.fixture
def client(monkeypatch):
    def fake_verify(token: str) -> dict:
        if token == "allowed-token":
            return {"uid": "uid-allowed", "email": "demo@example.test"}
        if token == "stranger-token":
            return {"uid": "uid-stranger", "email": "stranger@example.test"}
        raise auth.InvalidIdTokenError("bad token")

    monkeypatch.setattr(firebase, "verify_token", fake_verify)
    store = MemoryStore()
    store.videos["theirs"] = {"uid": "uid-allowed", "storagePath": "videos/uid-allowed/a.webm"}
    main.app.dependency_overrides[main.get_runner] = lambda: InlineRunner(store, None)
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


ROUTES = [
    ("get", "/me"),
    ("get", "/access"),
    ("post", "/videos/theirs/analyze"),
    ("post", "/videos/theirs/cancel"),
    ("post", "/videos/theirs/interpret"),
    ("delete", "/videos/theirs"),
    ("get", "/progress"),
    ("get", "/training/calendar"),
    ("delete", "/me"),
]


@pytest.mark.parametrize("method,path", ROUTES)
def test_an_account_that_is_not_listed_is_refused_by_the_backend(monkeypatch, client, method, path):
    env(monkeypatch, AQUATRACK_ACCESS="restricted", AQUATRACK_ALLOWED_UIDS="uid-allowed")
    kwargs = (
        {"json": {"confirm": "DELETE MY ACCOUNT"}} if (method, path) == ("delete", "/me") else {}
    )
    res = client.request(method, path, headers=STRANGER, **kwargs)
    assert res.status_code == 403, (path, res.status_code)
    assert res.json()["detail"] == config.ACCESS_DENIED
    assert client.request(method, path, **kwargs).status_code == 401  # no login at all


def test_every_route_that_takes_a_user_goes_through_the_same_check():
    """A route added later cannot skip the gate: anything that is not a health check must
    depend on current_user."""
    open_paths = {"/health", "/health/ready", "/openapi.json", "/docs", "/redoc"}
    for route in main.app.routes:
        if route.path in open_paths or route.path.startswith("/docs"):
            continue
        calls = {d.call for d in route.dependant.dependencies}
        assert firebase.current_user in calls, route.path


def test_a_listed_account_gets_in_and_open_mode_is_unchanged(monkeypatch, client):
    env(monkeypatch, AQUATRACK_ACCESS="restricted", AQUATRACK_ALLOWED_UIDS="uid-allowed")
    assert client.get("/me", headers=ALLOWED).status_code == 200
    assert client.get("/access", headers=ALLOWED).json() == {"access": "restricted", "demo": False}
    env(monkeypatch)
    assert client.get("/me", headers=STRANGER).status_code == 200


def test_claims_follow_the_list_and_no_account_is_created(monkeypatch):
    users = [
        SimpleNamespace(uid="uid-allowed", custom_claims=None),
        SimpleNamespace(uid="uid-kept", custom_claims={config.ACCESS_CLAIM: True}),
        SimpleNamespace(uid="uid-removed", custom_claims={config.ACCESS_CLAIM: True, "x": 1}),
        SimpleNamespace(uid="uid-stranger", custom_claims=None),
    ]
    calls = []
    monkeypatch.setattr(firebase, "_app", lambda: None)
    monkeypatch.setattr(
        auth, "list_users", lambda app=None: SimpleNamespace(iterate_all=lambda: iter(users))
    )
    monkeypatch.setattr(
        auth, "set_custom_user_claims", lambda uid, claims, app=None: calls.append((uid, claims))
    )
    monkeypatch.setattr(
        auth, "revoke_refresh_tokens", lambda uid, app=None: calls.append((uid, "revoked"))
    )
    counts = firebase.sync_access_claims(frozenset({"uid-allowed", "uid-kept", "uid-nobody"}))
    assert counts == {"granted": 1, "revoked": 1, "missing": 1}
    assert calls == [
        ("uid-allowed", {config.ACCESS_CLAIM: True}),
        ("uid-removed", {"x": 1}),
        ("uid-removed", "revoked"),
    ]


# --- where saved pose data may be used -----------------------------------------------------


def test_the_demonstration_configuration_is_valid_in_staging(monkeypatch):
    env(monkeypatch, **DEMO)
    assert config.validate("api") == []
    assert config.fixture_problem() is None


@pytest.mark.parametrize(
    "change,complaint",
    [
        ({"AQUATRACK_DEMO": "0"}, "development fixture"),
        ({"AQUATRACK_ACCESS": "open"}, "requires AQUATRACK_ACCESS=restricted"),
        ({"AQUATRACK_ALLOWED_UIDS": ""}, "nobody can sign in"),
        ({"AQUATRACK_ENV": "production"}, "never allowed in production"),
        ({"AQUATRACK_ENV": "production"}, "never used in production"),
        ({"FIRESTORE_EMULATOR_HOST": "127.0.0.1:8080"}, "must not use emulators"),
    ],
)
def test_saved_pose_data_cannot_serve_an_open_or_production_deployment(
    monkeypatch, change, complaint
):
    env(monkeypatch, **(DEMO | change))
    problems = config.validate("api")
    assert any(complaint in p for p in problems), problems


@pytest.mark.parametrize(
    "change",
    [{"AQUATRACK_DEMO": "0"}, {"AQUATRACK_ACCESS": "open"}, {"AQUATRACK_ENV": "production"}],
)
def test_the_process_refuses_to_build_the_fixture_source_outside_the_demo(monkeypatch, change):
    """Not only a logged warning: the job runner cannot be created at all."""
    env(monkeypatch, **(DEMO | change))
    with pytest.raises(RuntimeError):
        demo.build_pose_source(MemoryStore())


def test_local_development_keeps_using_the_fixture_as_before(monkeypatch, tmp_path):
    env(monkeypatch, AQUATRACK_ENV="test")
    monkeypatch.setenv("AQUATRACK_PRECOMPUTED_POSE_DIR", str(tmp_path))
    source = demo.build_pose_source(MemoryStore())
    assert isinstance(source, PrecomputedPoseSource)
    assert source.fetch is None and source.missing_retryable is True


class Bucket:
    """Stands in for the demonstration project's bucket: pose files by video hash."""

    def __init__(self, files: dict[str, Path]):
        self.files, self.asked = files, []

    def fetch_pose_fixture(self, sha256: str, dest: Path) -> bool:
        self.asked.append(sha256)
        if sha256 not in self.files:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.files[sha256].read_bytes())
        return True


def test_the_demo_matches_the_uploaded_file_by_hash_and_nothing_else(
    monkeypatch, tmp_path, swim_video, sample_video
):
    env(monkeypatch, **DEMO)
    monkeypatch.setenv("AQUATRACK_PRECOMPUTED_POSE_DIR", str(tmp_path / "cache"))
    approved = video_identity(swim_video)
    saved = tmp_path / "saved.npz"
    make_raw_pose(swim_video).save(saved)
    bucket = Bucket({approved.sha256: saved})
    source = demo.build_pose_source(bucket)

    raw = source.get_raw_pose(swim_video, approved, "vid-1")
    assert raw.meta.video.sha256 == approved.sha256
    assert raw.meta.provenance.source == "precomputed"  # recorded as saved data, not inference

    other = video_identity(sample_video)
    assert other.sha256 != approved.sha256
    with pytest.raises(PoseSourceError) as e:
        source.get_raw_pose(sample_video, other, "vid-2")
    assert e.value.code == "pose_data_missing" and e.value.retryable is False
    assert e.value.message == DEMO_UNSUPPORTED
    assert bucket.asked == [approved.sha256, other.sha256]  # only ever the upload's own hash


def test_saved_pose_data_under_the_wrong_hash_is_still_rejected(
    monkeypatch, tmp_path, swim_video, sample_video
):
    """Even if a pose file were stored under another video's hash, the usual comparison
    with the uploaded video refuses it."""
    env(monkeypatch, **DEMO)
    monkeypatch.setenv("AQUATRACK_PRECOMPUTED_POSE_DIR", str(tmp_path / "cache"))
    saved = tmp_path / "saved.npz"
    make_raw_pose(swim_video).save(saved)
    other = video_identity(sample_video)
    source = demo.build_pose_source(Bucket({other.sha256: saved}))
    with pytest.raises(PoseSourceError) as e:
        source.get_raw_pose(sample_video, other, "vid-2")
    assert e.value.code != "pose_data_missing"


def test_a_bucket_failure_is_a_retryable_error_not_a_made_up_result(
    monkeypatch, tmp_path, swim_video
):
    env(monkeypatch, **DEMO)
    monkeypatch.setenv("AQUATRACK_PRECOMPUTED_POSE_DIR", str(tmp_path / "cache"))

    class Broken:
        def fetch_pose_fixture(self, sha256, dest):
            raise OSError("network")

    source = demo.build_pose_source(Broken())
    with pytest.raises(PoseSourceError) as e:
        source.get_raw_pose(swim_video, video_identity(swim_video), "vid-1")
    assert e.value.code == "pose_data_unavailable" and e.value.retryable is True


# --- the restricted security rules ---------------------------------------------------------


def test_the_restricted_rules_are_generated_from_the_current_rules():
    done = subprocess.run(
        [sys.executable, "scripts/build_restricted_rules.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.parametrize("name", ["firestore.rules", "storage.rules"])
def test_no_restricted_rule_accepts_a_sign_in_without_the_claim(name):
    text = (ROOT / "firebase/restricted" / name).read_text()
    claim = f"request.auth.token.{config.ACCESS_CLAIM} == true"
    assert text.count("request.auth != null") == text.count(f"request.auth != null && {claim}") > 0
