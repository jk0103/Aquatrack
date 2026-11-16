"""Account deletion, request limits, environment checks and the health endpoints. Every
account here is a disposable test fixture."""
# ruff: noqa: E501

import pytest
from fastapi.testclient import TestClient
from firebase_admin import auth
from test_queue import FakeInference, add_video
from test_training import MON, profile

from aquatrack.api import account, config, firebase, jobs, limits, main, training
from aquatrack.api.account import CONFIRM_PHRASE, AccountError, delete_account
from aquatrack.api.jobs import InlineRunner
from aquatrack.api.store import MemoryStore

UID, OTHER = "swimmer-1", "swimmer-2"


@pytest.fixture
def store(swim_video):
    s = MemoryStore()
    for uid, vid in ((UID, "mine"), (OTHER, "theirs")):
        s.profiles[uid] = profile()
        add_video(s, swim_video, vid, uid=uid)
        jobs.request_analysis(s, vid, uid)
        jobs.run_job(s, FakeInference(swim_video), vid)
        training.save_plan(s, uid, "week", MON)
    add_video(s, swim_video, "mine-queued")
    jobs.request_analysis(s, "mine-queued", UID)
    return s


def everything(store) -> str:
    return str(
        [
            store.videos,
            store.files.keys(),
            store.analyses,
            store.interpretations,
            store.feedback,
            store.profiles,
            store.docs,
        ]
    )


def test_deleting_an_account_removes_everything_it_owns_and_nothing_else(store):
    removed = []
    theirs_before = {k: v for k, v in store.docs["training_sessions"].items() if v["uid"] == OTHER}
    out = delete_account(store, UID, CONFIRM_PHRASE, removed.append)
    assert out == {"deleted": True, "resumed": False, "videos": 2, "training": out["training"]}
    assert out["training"] >= 5 and removed == [
        UID
    ]  # sessions, plan, schedule state; then the sign-in
    assert UID not in everything(store)
    assert not account.is_deleting(store, UID)  # the marker goes last
    # the other swimmer's account is untouched
    assert store.videos["theirs"]["status"] == "ready" and OTHER in store.profiles
    assert {
        k: v for k, v in store.docs["training_sessions"].items() if v["uid"] == OTHER
    } == theirs_before
    assert any(f.startswith(f"analysis/{OTHER}/") for f in store.files)


@pytest.mark.parametrize("confirm", [None, "", "yes", "delete my account", True])
def test_nothing_is_deleted_without_the_exact_confirmation(store, confirm):
    before = everything(store)
    with pytest.raises(AccountError) as e:
        delete_account(store, UID, confirm, lambda uid: None)
    assert e.value.status_code == 422 and everything(store) == before


def test_no_new_work_can_start_while_an_account_is_being_deleted(store, monkeypatch):
    monkeypatch.setattr(store, "delete_profile", lambda uid: (_ for _ in ()).throw(OSError("x")))
    with pytest.raises(AccountError) as e:
        delete_account(store, UID, CONFIRM_PHRASE, lambda uid: None)
    assert e.value.status_code == 503 and "try again" in e.value.detail and "x" != e.value.detail
    assert account.is_deleting(store, UID)
    with pytest.raises(AccountError, match="being deleted"):
        account.guard(store, UID)
    account.guard(store, OTHER)  # nobody else is affected


@pytest.mark.parametrize("fail_at", ["videos", "training", "profile", "sign_in", "marker"])
def test_a_deletion_that_stops_part_way_is_finished_by_asking_again(store, monkeypatch, fail_at):
    boom = lambda *a, **k: (_ for _ in ()).throw(ConnectionError("lost"))  # noqa: E731
    with monkeypatch.context() as m:
        if fail_at == "videos":
            m.setattr(store, "fail_delete_at", "documents", raising=False)
        elif fail_at == "training":
            m.setattr(store, "list_docs", boom)
        elif fail_at == "profile":
            m.setattr(store, "delete_profile", boom)
        elif fail_at == "marker":
            real = store.delete_doc
            m.setattr(
                store, "delete_doc", lambda c, i: boom() if c == "account_deletions" else real(c, i)
            )
        with pytest.raises(AccountError) as e:
            delete_account(
                store, UID, CONFIRM_PHRASE, boom if fail_at == "sign_in" else lambda uid: None
            )
        assert e.value.status_code == 503 and "lost" not in e.value.detail
    assert account.is_deleting(store, UID)
    out = delete_account(store, UID, CONFIRM_PHRASE, lambda uid: None)
    assert out["deleted"] and out["resumed"] is True
    assert UID not in everything(store)
    assert delete_account(store, UID, CONFIRM_PHRASE, lambda uid: None)[
        "deleted"
    ]  # and again: fine


def test_a_running_analysis_stores_nothing_for_an_account_that_was_deleted(store, swim_video):
    def account_is_deleted(call):
        delete_account(store, UID, CONFIRM_PHRASE, lambda uid: None)

    jobs.run_job(store, FakeInference(swim_video, account_is_deleted), "mine-queued")
    assert UID not in everything(store)


# ---------- over HTTP ----------

GOOD = {"Authorization": "Bearer good-token"}


@pytest.fixture
def client(monkeypatch, store, swim_video):
    def fake_verify(token: str) -> dict:
        if token == "good-token":
            return {"uid": UID}
        raise auth.InvalidIdTokenError("bad token")

    gone = []
    monkeypatch.setattr(firebase, "verify_token", fake_verify)
    monkeypatch.setattr(main, "delete_auth_user", gone.append)
    main.app.dependency_overrides[main.get_runner] = lambda: InlineRunner(
        store, FakeInference(swim_video)
    )
    c = TestClient(main.app)
    c.gone = gone
    yield c
    main.app.dependency_overrides.clear()


def test_account_deletion_over_http_needs_a_login_and_the_phrase(client, store):
    assert client.request("DELETE", "/me", json={"confirm": CONFIRM_PHRASE}).status_code == 401
    res = client.request("DELETE", "/me", headers=GOOD, json={"confirm": "please"})
    assert res.status_code == 422 and CONFIRM_PHRASE in res.json()["detail"]
    res = client.request("DELETE", "/me", headers=GOOD, json={"confirm": CONFIRM_PHRASE})
    assert res.status_code == 200 and res.json()["deleted"] and client.gone == [UID]
    assert (
        UID not in everything(store) and "videos/" not in res.text and "analysis/" not in res.text
    )


def test_writes_are_refused_over_http_while_the_account_is_being_deleted(client, store):
    store.set_doc("account_deletions", UID, {"uid": UID, "id": UID})
    for method, path, body in [
        ("post", "/videos/mine/analyze?rerun=true", None),
        ("post", "/videos/mine/interpret", None),
        ("post", "/training/plans", {"kind": "week", "start": "2026-11-16", "token": "x"}),
        ("post", "/training/sessions", {"date": "2026-11-16", "title": "x", "items": []}),
    ]:
        res = getattr(client, method)(path, headers=GOOD, **({"json": body} if body else {}))
        assert (
            res.status_code == 409 and res.json()["detail"] == "This account is being deleted."
        ), path
    assert (
        client.get("/training?today=2026-11-16", headers=GOOD).status_code == 200
    )  # reading still works


def test_cancel_over_http(client, store, swim_video):
    add_video(store, swim_video, "v3")
    store.videos["v3"] |= {"status": "queued", "job": {"attempts": 1}}
    assert client.post("/videos/v3/cancel").status_code == 401
    assert client.post("/videos/v3/cancel", headers=GOOD).json() == {
        "id": "v3",
        "status": "canceled",
    }
    assert client.post("/videos/theirs/cancel", headers=GOOD).status_code == 404
    assert client.post("/videos/mine/cancel", headers=GOOD).status_code == 409


# ---------- request limits ----------


def test_requests_over_the_limit_are_refused_with_a_wait_time_per_swimmer():
    lim = limits.RateLimiter()
    allowed, window = limits.LIMITS["account"]
    assert all(lim.retry_after("a", "account", now=float(n)) == 0 for n in range(allowed))
    wait = lim.retry_after("a", "account", now=float(allowed))
    assert 0 < wait <= window + 1
    assert lim.retry_after("b", "account", now=float(allowed)) == 0  # another swimmer is unaffected
    assert lim.retry_after("a", "write", now=float(allowed)) == 0  # another kind of request too
    assert (
        lim.retry_after("a", "account", now=float(window + allowed)) == 0
    )  # and it passes with time


def test_the_api_answers_429_with_retry_after(client, monkeypatch):
    monkeypatch.setitem(limits.LIMITS, "read", (2, 60))
    codes = [client.get("/progress", headers=GOOD).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    res = client.get("/progress", headers=GOOD)
    assert int(res.headers["Retry-After"]) >= 1 and "Too many requests" in res.json()["detail"]


# ---------- environments ----------

EMULATORS = {
    "FIREBASE_AUTH_EMULATOR_HOST": "127.0.0.1:9099",
    "FIRESTORE_EMULATOR_HOST": "127.0.0.1:8080",
    "STORAGE_EMULATOR_HOST": "http://127.0.0.1:9199",
}
REAL = {
    "AQUATRACK_ENV": "production",
    "FIREBASE_PROJECT_ID": "aquatrack-live",
    "AQUATRACK_ALLOW_PRODUCTION_FIREBASE": "1",
    "AQUATRACK_WORKER": "external",
    "AQUATRACK_POSE_SOURCE": "local",
}
ALL = [
    *EMULATORS,
    *REAL,
    "GOOGLE_APPLICATION_CREDENTIALS",
    "AQUATRACK_LLM_PROVIDER",
    "OPENAI_API_KEY",
]


def configured(monkeypatch, **env):
    for name in ALL:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return config.validate


def test_the_local_emulator_setup_is_valid(monkeypatch):
    assert configured(monkeypatch, **EMULATORS, FIREBASE_PROJECT_ID="demo-aquatrack")() == []
    assert configured(monkeypatch, AQUATRACK_ENV="test")() == []


@pytest.mark.parametrize(
    "env,complaint",
    [
        (
            {**EMULATORS, "GOOGLE_APPLICATION_CREDENTIALS": "/keys/prod.json"},
            "must never hold credentials",
        ),
        ({**EMULATORS, "FIREBASE_PROJECT_ID": "aquatrack-live"}, "must start with 'demo-'"),
        ({**EMULATORS, "AQUATRACK_ALLOW_PRODUCTION_FIREBASE": "1"}, "not allowed locally"),
        ({"FIRESTORE_EMULATOR_HOST": "127.0.0.1:8080"}, "Emulator hosts are not all set"),
        ({"AQUATRACK_ENV": "prod"}, "must be one of"),
        ({**REAL, **EMULATORS}, "must not use emulators"),
        (
            {**REAL, "FIREBASE_PROJECT_ID": "demo-aquatrack"},
            "must name the real production project",
        ),
        ({**REAL, "AQUATRACK_ALLOW_PRODUCTION_FIREBASE": "0"}, "is required to use a real project"),
        ({**REAL, "AQUATRACK_WORKER": "embedded"}, "worker as its own process"),
        ({**EMULATORS, "AQUATRACK_LLM_PROVIDER": "openai"}, "needs OPENAI_API_KEY"),
        ({**EMULATORS, "AQUATRACK_LLM_PROVIDER": "claude"}, "must be empty or 'openai'"),
    ],
)
def test_a_configuration_that_could_touch_the_wrong_data_is_refused(monkeypatch, env, complaint):
    problems = configured(monkeypatch, **env)()
    assert any(complaint in p for p in problems), problems


def test_a_production_worker_cannot_run_on_the_precomputed_fixture(monkeypatch):
    validate = configured(monkeypatch, **(REAL | {"AQUATRACK_POSE_SOURCE": "precomputed"}))
    assert any("development fixture" in p for p in validate(role="worker"))
    assert configured(monkeypatch, **REAL)(role="worker") == []
    assert configured(monkeypatch, **REAL)(role="api") == []


def test_configuration_messages_never_contain_a_secret(monkeypatch):
    validate = configured(
        monkeypatch,
        **EMULATORS,
        AQUATRACK_ENV="staging",
        OPENAI_API_KEY="sk-secret-value",
        GOOGLE_APPLICATION_CREDENTIALS="/keys/secret.json",
    )
    text = " ".join(validate())
    assert text and "sk-secret-value" not in text and "/keys/secret.json" not in text


def test_the_store_refuses_a_real_project_unless_the_environment_says_so(monkeypatch):
    from aquatrack.api.store import FirebaseStore

    configured(monkeypatch, AQUATRACK_ALLOW_PRODUCTION_FIREBASE="1")  # env still "emulator"
    with pytest.raises(RuntimeError, match="AQUATRACK_ENV=staging"):
        FirebaseStore()


def test_health_says_alive_and_readiness_reports_counts_only(client, store, monkeypatch):
    assert client.get("/health").json()["status"] == "ok"
    monkeypatch.setattr(main, "get_runner", lambda: InlineRunner(store, None))
    configured(monkeypatch, **EMULATORS)
    body = client.get("/health/ready").json()
    assert body == {
        "status": "ready",
        "environment": "emulator",
        "worker": "embedded",
        "queue": {"queued": 1, "analyzing": 0},
    }
    configured(monkeypatch, **EMULATORS, GOOGLE_APPLICATION_CREDENTIALS="/keys/prod.json")
    bad = client.get("/health/ready")
    assert (
        bad.status_code == 503 and "/keys" not in bad.text and bad.json()["detail"]["problems"] == 1
    )
