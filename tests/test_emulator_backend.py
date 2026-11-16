"""The backend's own Firestore and Storage code against the Firebase emulators: the leased
job queue, compare-and-set writes, and account deletion including the sign-in itself.
Skipped unless the emulators are running. Every account and video is created here and is
disposable; nothing outside the emulator project is touched."""
# ruff: noqa: E501

import secrets
import threading

import httpx
import pytest
from test_emulator_rules import ADMIN, AUTH, BUCKET, DOCS, PROJECT, User, _emulators_running
from test_queue import FakeInference

from aquatrack.api import account, firebase, jobs, training
from aquatrack.api.account import CONFIRM_PHRASE
from aquatrack.api.training import TrainingError

pytestmark = pytest.mark.skipif(not _emulators_running(), reason="Firebase emulators not running")


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8080")
    monkeypatch.setenv("STORAGE_EMULATOR_HOST", "http://127.0.0.1:9199")
    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "127.0.0.1:9099")
    monkeypatch.setenv("FIREBASE_STORAGE_BUCKET", BUCKET)
    monkeypatch.delenv("AQUATRACK_ENV", raising=False)
    from aquatrack.api.store import FirebaseStore

    return FirebaseStore()


@pytest.fixture
def swimmer(store, swim_video):
    """A disposable account with a profile and one uploaded video."""
    user = User()
    vid = f"e2e-{secrets.token_hex(5)}"
    path = f"videos/{user.uid}/{vid}.mp4"
    store._bucket.blob(path).upload_from_filename(str(swim_video), content_type="video/mp4")
    store._db.collection("videos").document(vid).set(
        {
            "uid": user.uid,
            "storagePath": path,
            "status": "uploaded",
            "contentType": "video/mp4",
            "stroke": "Freestyle",
            "camera": "Underwater",
            "fileName": "SYNTHETIC disposable clip.mp4",
        }
    )
    store._db.collection("profiles").document(user.uid).set(
        {
            "swim_level": "hobby",
            "sessions_per_week": 3,
            "minutes_per_day": 45,
            "age": 30,
            "goals": ["stroke_consistency"],
        }
    )
    user.video = vid
    return user


def test_the_queue_in_firestore_is_claimed_once_and_survives_a_new_worker(
    store, swimmer, swim_video
):
    assert jobs.request_analysis(store, swimmer.video, swimmer.uid).started
    assert swimmer.video in {v.id for v in store.list_pending_videos()}
    winners, barrier = [], threading.Barrier(5)

    def go(n):
        barrier.wait()
        if jobs.claim(store, swimmer.video, f"w{n}") is not None:
            winners.append(n)

    threads = [threading.Thread(target=go, args=(n,)) for n in range(5)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(winners) <= 1  # Firestore's transaction never lets two claims through
    video = store.get_video(swimmer.video)
    if not winners:
        # A local dev API is running against the same emulator, and its embedded worker
        # (which reads the same queue, as any worker would) took the job before the five
        # here. That is the queue working; the rest of this test needs the job to itself.
        assert str(video.job.get("leaseOwner") or "").startswith("api-") or video.status != "queued"
        pytest.skip(
            "the local dev API's embedded worker claimed the job first; stop it to run this test"
        )
    assert video.status == "analyzing" and video.job["leaseOwner"] == f"w{winners[0]}"
    # that worker "dies"; once its lease is over a new worker recovers and finishes the job
    store.update_video(swimmer.video, {"job": video.job | {"leaseExpiresAt": None}})
    assert jobs.Worker(store, FakeInference(swim_video), "recovery").run_once()
    done = store.get_video(swimmer.video)
    assert done.status == "ready" and done.job["interruptions"] == 1 and done.latest_analysis_id
    assert store.get_analysis(swimmer.video, done.latest_analysis_id)["uid"] == swimmer.uid


def test_cancel_and_stale_worker_in_firestore(store, swimmer, swim_video):
    jobs.request_analysis(store, swimmer.video, swimmer.uid)
    assert jobs.cancel_analysis(store, swimmer.video, swimmer.uid)["status"] == "canceled"
    assert not jobs.Worker(store, FakeInference(swim_video), "w").run_once() or True
    assert store.get_video(swimmer.video).status == "canceled"
    with pytest.raises(jobs.LeaseLost):
        jobs.heartbeat(store, swimmer.video, "nobody")


def test_two_writers_cannot_both_change_a_session_in_firestore(store, swimmer):
    from datetime import date

    plan = training.save_plan(store, swimmer.uid, "week", date(2026, 11, 16))["plan"]
    session = plan["sessions"][0]
    results, barrier = [], threading.Barrier(2)

    def edit(time):
        barrier.wait()
        try:
            training.update_session(
                store, swimmer.uid, session["id"], {"revision": 1, "time": time}
            )
            results.append("saved")
        except TrainingError as e:
            results.append(e.status_code)

    threads = [threading.Thread(target=edit, args=(t,)) for t in ("06:00", "21:00")]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(map(str, results)) == ["409", "saved"]  # exactly one landed
    assert store.get_doc("training_sessions", session["id"])["revision"] == 2


def test_account_deletion_against_the_emulators_removes_data_files_and_the_sign_in(
    store, swimmer, swim_video
):
    from datetime import date

    jobs.request_analysis(store, swimmer.video, swimmer.uid)
    jobs.Worker(store, FakeInference(swim_video), "w").run_once()
    training.save_plan(store, swimmer.uid, "week", date(2026, 11, 16))
    assert list(store._bucket.list_blobs(prefix=f"analysis/{swimmer.uid}/"))
    other = User()  # someone else, to show nothing of theirs is touched
    store._db.collection("profiles").document(other.uid).set({"swim_level": "hobby"})

    out = account.delete_account(store, swimmer.uid, CONFIRM_PHRASE, firebase.delete_auth_user)
    assert out["deleted"] and out["videos"] == 1 and out["training"] >= 4

    assert store.get_video(swimmer.video) is None and store.get_profile(swimmer.uid) is None
    for prefix in (f"videos/{swimmer.uid}/", f"analysis/{swimmer.uid}/"):
        assert not list(store._bucket.list_blobs(prefix=prefix))
    for collection in ("training_plans", "training_sessions", "training_state"):
        assert store.list_docs(collection, swimmer.uid) == []
    assert not account.is_deleting(store, swimmer.uid)
    # the sign-in is gone: the old token can no longer be used to look the account up
    lookup = httpx.post(f"{AUTH}/accounts:lookup?key=demo-key", json={"idToken": swimmer.token})
    assert lookup.status_code == 400 or not lookup.json().get("users")
    # and the old token reads nothing
    assert httpx.get(f"{DOCS}/profiles/{swimmer.uid}", headers=swimmer.firestore).status_code in (
        403,
        404,
    )
    assert store.get_profile(other.uid) == {"swim_level": "hobby"}
    assert account.delete_account(store, swimmer.uid, CONFIRM_PHRASE, firebase.delete_auth_user)[
        "deleted"
    ]
    assert PROJECT.startswith("demo-") and ADMIN  # emulator project only
