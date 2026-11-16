"""Where videos, job state and analysis results live.

`FirebaseStore` talks to Firestore and Storage with admin rights (the web app's security
rules do not let clients write job state or results). `MemoryStore` is the same interface
in memory, for tests.

Firestore layout:
  videos/{id}                      the upload record; the backend adds `status`, `job`,
                                   `latestAnalysisId` and a small `analysisSummary`
  videos/{id}/analyses/{analysisId}  one AnalysisResult (structured, no per-frame arrays)
  videos/{id}/interpretations/{interpretationId}  one Interpretation of a stored analysis;
                                   a new document per run, earlier ones are never changed
  videos/{id}/feedback/{feedbackId}  feedback built from one interpretation; the id is a
                                   hash of its inputs, and an existing document is kept
  profiles/{uid}                   the swimmer's own survey answers (read only here)
  training_plans/{id}              one version of a training plan (see docs/TRAINING.md)
  training_sessions/{id}           one planned or manually created swimming session
  training_state/{uid}             the revision counter of one swimmer's schedule
  account_deletions/{uid}          present only while that account is being deleted
Storage layout:
  videos/{uid}/{id}.{ext}          the uploaded video (written by the web app)
  analysis/{uid}/{id}/{analysisId}/raw_pose.npz, processed_pose.npz   per-frame arrays
"""

import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from aquatrack.api.config import FIREBASE_PROJECT_ID, is_real_project
from aquatrack.contracts import SessionInfo

EMULATOR_PROJECT = "demo-aquatrack"


@dataclass
class VideoRecord:
    id: str
    uid: str
    storage_path: str
    status: str
    content_type: str = ""
    size_bytes: int = 0
    job: dict[str, Any] = field(default_factory=dict)
    session: SessionInfo = field(default_factory=SessionInfo)
    latest_analysis_id: str = ""
    latest_interpretation_id: str = ""
    latest_feedback_id: str = ""
    file_name: str = ""
    interpretation_summary: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""  # ISO time of the upload, for ordering a swimmer's sessions


# Given the current record (None if the video doesn't exist), return the fields to merge
# into the video document (or None to leave it) and a value to hand back to the caller.
Decide = Callable[[VideoRecord | None], tuple[dict[str, Any] | None, Any]]


class Store(Protocol):
    def get_video(self, video_id: str) -> VideoRecord | None: ...

    def transact(self, video_id: str, decide: Decide) -> Any:
        """Read the video and apply `decide` atomically, so two requests can't both queue."""
        ...

    def update_video(self, video_id: str, fields: dict[str, Any]) -> None: ...

    def download_video(self, storage_path: str, dest: Path) -> None: ...

    def save_analysis(
        self,
        video: VideoRecord,
        analysis_id: str,
        result: dict[str, Any],
        files: dict[str, Path],
    ) -> dict[str, tuple[str, int]]:
        """Store the result document and artifact files; returns {name: (path, bytes)}."""
        ...

    def get_analysis(self, video_id: str, analysis_id: str) -> dict[str, Any] | None: ...

    def list_videos(self, uid: str) -> list[VideoRecord]:
        """All of one swimmer's video records (never anyone else's)."""
        ...

    def list_pending_videos(self) -> list[VideoRecord]:
        """Every video, of any swimmer, that is queued or being analysed: the job queue.
        Only workers call this; nothing from it is ever returned to a client."""
        ...

    def get_profile(self, uid: str) -> dict[str, Any] | None: ...

    def save_interpretation(
        self, video: VideoRecord, interpretation_id: str, document: dict[str, Any]
    ) -> None:
        """Add one interpretation document. Never replaces an existing one."""
        ...

    def save_feedback(self, video: VideoRecord, feedback_id: str, document: dict[str, Any]) -> bool:
        """Add a feedback document unless one with this id exists. Returns True if added."""
        ...

    def get_feedback(self, video_id: str, feedback_id: str) -> dict[str, Any] | None: ...

    def get_interpretation(
        self, video_id: str, interpretation_id: str
    ) -> dict[str, Any] | None: ...

    def delete_video_data(self, video: VideoRecord) -> None:
        """Remove everything stored for one video: its analysis artifacts and video file in
        Storage, its analyses, interpretations and feedback, and last the video record
        itself. Every step tolerates data that is already gone, so it can be run again
        after a failure. Raises if a step fails; the video record then still exists."""
        ...

    def get_doc(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        """One training document (with its owner's `uid`), or None."""
        ...

    def set_doc(self, collection: str, doc_id: str, document: dict[str, Any]) -> None: ...

    def delete_doc(self, collection: str, doc_id: str) -> None: ...

    def list_docs(self, collection: str, uid: str) -> list[dict[str, Any]]:
        """All of one swimmer's documents in a training collection (never anyone else's)."""
        ...

    def swap_doc(
        self, collection: str, doc_id: str, expected_revision: int | None, document: dict[str, Any]
    ) -> bool:
        """Write the document only if what is stored still has `expected_revision` (None:
        only if nothing is stored). Atomic. False means someone else changed it first, and
        nothing was written."""
        ...

    def delete_profile(self, uid: str) -> None: ...


# Collections the training code may use through the generic document methods below.
TRAINING_COLLECTIONS = (
    "training_plans",
    "training_sessions",
    "training_state",  # one small document per swimmer: the revision of their schedule
    "account_deletions",  # a marker while an account is being deleted
)


def _record(video_id: str, data: dict[str, Any]) -> VideoRecord:
    return VideoRecord(
        id=video_id,
        uid=str(data.get("uid", "")),
        storage_path=str(data.get("storagePath", "")),
        status=str(data.get("status", "uploaded")),
        content_type=str(data.get("contentType", "")),
        size_bytes=int(data.get("sizeBytes", 0) or 0),
        job=dict(data.get("job") or {}),
        latest_analysis_id=str(data.get("latestAnalysisId") or ""),
        latest_interpretation_id=str(data.get("latestInterpretationId") or ""),
        latest_feedback_id=str(data.get("latestFeedbackId") or ""),
        file_name=str(data.get("fileName") or ""),
        interpretation_summary=dict(data.get("interpretationSummary") or {}),
        created_at=_iso(data.get("createdAt")),
        session=SessionInfo(
            stroke=str(data.get("stroke", "")),
            camera=str(data.get("camera", "")),
            distance=str(data.get("distance", "")),
            pool_length=str(data.get("poolLength", "")),
        ),
    )


def _iso(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value) if value else ""


def artifact_path(video: VideoRecord, analysis_id: str, name: str) -> str:
    return f"analysis/{video.uid}/{video.id}/{analysis_id}/{name}"


def _document(video: VideoRecord, result: dict, saved: dict[str, tuple[str, int]]) -> dict:
    """The analysis document: the result, its owner, and where the big arrays are."""
    artifacts = [
        {"kind": Path(name).stem, "storage_path": path, "bytes": size}
        for name, (path, size) in saved.items()
    ]
    return {**result, "uid": video.uid, "artifacts": artifacts}


def _training(collection: str) -> str:
    if collection not in TRAINING_COLLECTIONS:
        raise ValueError(f"not a training collection: {collection}")
    return collection


class MemoryStore:
    """In-memory Store for tests. `videos` maps id -> Firestore-style document dict."""

    def __init__(self):
        self.videos: dict[str, dict[str, Any]] = {}
        self.files: dict[str, bytes] = {}
        self.analyses: dict[tuple[str, str], dict[str, Any]] = {}
        self.interpretations: dict[tuple[str, str], dict[str, Any]] = {}
        self.profiles: dict[str, dict[str, Any]] = {}
        self.feedback: dict[tuple[str, str], dict[str, Any]] = {}
        self.docs: dict[str, dict[str, dict[str, Any]]] = {c: {} for c in TRAINING_COLLECTIONS}
        self._lock = threading.Lock()

    def get_video(self, video_id: str) -> VideoRecord | None:
        data = self.videos.get(video_id)
        return None if data is None else _record(video_id, data)

    def transact(self, video_id: str, decide: Decide) -> Any:
        with self._lock:
            updates, value = decide(self.get_video(video_id))
            if updates is not None:
                self.videos[video_id].update(updates)
            return value

    def update_video(self, video_id: str, fields: dict[str, Any]) -> None:
        with self._lock:
            if video_id in self.videos:  # never bring a deleted record back
                self.videos[video_id].update(fields)

    def download_video(self, storage_path: str, dest: Path) -> None:
        dest.write_bytes(self.files[storage_path])

    def save_analysis(self, video, analysis_id, result, files):
        saved = {}
        for name, path in files.items():
            target = artifact_path(video, analysis_id, name)
            self.files[target] = Path(path).read_bytes()
            saved[name] = (target, len(self.files[target]))
        self.analyses[(video.id, analysis_id)] = _document(video, result, saved)
        return saved

    def get_analysis(self, video_id, analysis_id):
        return self.analyses.get((video_id, analysis_id))

    def list_videos(self, uid):
        return [_record(k, v) for k, v in self.videos.items() if v.get("uid") == uid]

    def list_pending_videos(self):
        return [
            _record(k, v)
            for k, v in self.videos.items()
            if v.get("status") in ("queued", "analyzing")
        ]

    def get_profile(self, uid):
        return self.profiles.get(uid)

    def save_interpretation(self, video, interpretation_id, document):
        key = (video.id, interpretation_id)
        if key in self.interpretations:
            raise ValueError("An interpretation with this id already exists.")
        self.interpretations[key] = {**document, "uid": video.uid}

    def save_feedback(self, video, feedback_id, document):
        key = (video.id, feedback_id)
        if key in self.feedback:
            return False
        self.feedback[key] = {**document, "uid": video.uid}
        return True

    def get_feedback(self, video_id, feedback_id):
        return self.feedback.get((video_id, feedback_id))

    def get_interpretation(self, video_id, interpretation_id):
        return self.interpretations.get((video_id, interpretation_id))

    def delete_video_data(self, video):
        # `fail_delete_at` (a step name) lets tests stop part-way, like a lost connection.
        def step(name):
            if getattr(self, "fail_delete_at", None) == name:
                raise RuntimeError(f"simulated failure at {name}")

        step("artifacts")
        prefix = f"analysis/{video.uid}/{video.id}/"
        for path in [p for p in self.files if p.startswith(prefix)]:
            del self.files[path]
        step("video_file")
        if video.storage_path.startswith(f"videos/{video.uid}/"):
            self.files.pop(video.storage_path, None)
        step("documents")
        for table in (self.feedback, self.interpretations, self.analyses):
            for key in [k for k in table if k[0] == video.id]:
                del table[key]
        step("record")
        with self._lock:
            self.videos.pop(video.id, None)

    def get_doc(self, collection, doc_id):
        doc = self.docs[_training(collection)].get(doc_id)
        return None if doc is None else dict(doc)

    def set_doc(self, collection, doc_id, document):
        self.docs[_training(collection)][doc_id] = dict(document)

    def delete_doc(self, collection, doc_id):
        self.docs[_training(collection)].pop(doc_id, None)

    def list_docs(self, collection, uid):
        return [dict(d) for d in self.docs[_training(collection)].values() if d.get("uid") == uid]

    def swap_doc(self, collection, doc_id, expected_revision, document):
        with self._lock:
            stored = self.docs[_training(collection)].get(doc_id)
            current = None if stored is None else int(stored.get("revision", 0) or 0)
            if current != expected_revision:
                return False
            self.docs[collection][doc_id] = dict(document)
            return True

    def delete_profile(self, uid):
        self.profiles.pop(uid, None)


class FirebaseStore:
    """Firestore + Storage through the Google Cloud clients.

    Emulator only for now: unless AQUATRACK_ALLOW_PRODUCTION_FIREBASE=1 is set, it refuses
    to start when the emulator hosts are not configured, so a missing environment variable
    can never point development code at a real project.
    """

    def __init__(self):
        from google.cloud import firestore, storage

        firestore_emulator = os.environ.get("FIRESTORE_EMULATOR_HOST")
        storage_emulator = os.environ.get("STORAGE_EMULATOR_HOST")
        emulated = bool(firestore_emulator and storage_emulator)
        if not emulated and not (
            os.environ.get("AQUATRACK_ALLOW_PRODUCTION_FIREBASE") == "1" and is_real_project()
        ):
            raise RuntimeError(
                "Firebase emulators are not configured (FIRESTORE_EMULATOR_HOST and "
                "STORAGE_EMULATOR_HOST). A real Firebase project needs AQUATRACK_ENV=staging "
                "or production together with AQUATRACK_ALLOW_PRODUCTION_FIREBASE=1."
            )
        project = FIREBASE_PROJECT_ID or EMULATOR_PROJECT
        bucket = os.environ.get("FIREBASE_STORAGE_BUCKET", f"{project}.appspot.com")
        if emulated:
            from google.auth.credentials import AnonymousCredentials

            credentials = AnonymousCredentials()
            self._db = firestore.Client(project=project, credentials=credentials)
            self._bucket = storage.Client(project=project, credentials=credentials).bucket(bucket)
        else:
            self._db = firestore.Client(project=project)
            self._bucket = storage.Client(project=project).bucket(bucket)
        self._firestore = firestore

    def _ref(self, video_id: str):
        return self._db.collection("videos").document(video_id)

    def get_video(self, video_id: str) -> VideoRecord | None:
        snap = self._ref(video_id).get()
        return _record(video_id, snap.to_dict()) if snap.exists else None

    def transact(self, video_id: str, decide: Decide) -> Any:
        ref = self._ref(video_id)

        @self._firestore.transactional
        def run(transaction):
            snap = ref.get(transaction=transaction)
            updates, value = decide(_record(video_id, snap.to_dict()) if snap.exists else None)
            if updates is not None:
                transaction.set(ref, updates, merge=True)
            return value

        return run(self._db.transaction())

    def update_video(self, video_id: str, fields: dict[str, Any]) -> None:
        from google.api_core.exceptions import NotFound

        try:
            self._ref(video_id).update(fields)  # unlike set(merge), never recreates the record
        except NotFound:
            pass  # deleted in the meantime: nothing to update

    def download_video(self, storage_path: str, dest: Path) -> None:
        self._bucket.blob(storage_path).download_to_filename(str(dest))

    def save_analysis(self, video, analysis_id, result, files):
        saved = {}
        for name, path in files.items():
            target = artifact_path(video, analysis_id, name)
            self._bucket.blob(target).upload_from_filename(
                str(path), content_type="application/octet-stream"
            )
            saved[name] = (target, Path(path).stat().st_size)
        self._ref(video.id).collection("analyses").document(analysis_id).set(
            _document(video, result, saved)
        )
        return saved

    def get_analysis(self, video_id, analysis_id):
        snap = self._ref(video_id).collection("analyses").document(analysis_id).get()
        return snap.to_dict() if snap.exists else None

    def list_videos(self, uid):
        query = self._db.collection("videos").where("uid", "==", uid)
        return [_record(snap.id, snap.to_dict()) for snap in query.stream()]

    def list_pending_videos(self):
        query = self._db.collection("videos").where("status", "in", ["queued", "analyzing"])
        return [_record(snap.id, snap.to_dict()) for snap in query.stream()]

    def get_profile(self, uid):
        snap = self._db.collection("profiles").document(uid).get()
        return snap.to_dict() if snap.exists else None

    def save_interpretation(self, video, interpretation_id, document):
        ref = self._ref(video.id).collection("interpretations").document(interpretation_id)
        ref.create({**document, "uid": video.uid})  # fails rather than overwrite

    def save_feedback(self, video, feedback_id, document):
        ref = self._ref(video.id).collection("feedback").document(feedback_id)
        if ref.get().exists:
            return False  # same inputs, same feedback: keep what is there
        ref.create({**document, "uid": video.uid})
        return True

    def get_feedback(self, video_id, feedback_id):
        snap = self._ref(video_id).collection("feedback").document(feedback_id).get()
        return snap.to_dict() if snap.exists else None

    def get_interpretation(self, video_id, interpretation_id):
        snap = self._ref(video_id).collection("interpretations").document(interpretation_id).get()
        return snap.to_dict() if snap.exists else None

    def delete_video_data(self, video):
        from google.api_core.exceptions import NotFound

        # Storage first, the record last: if anything fails the record (status "deleting")
        # is still there to find what is left and try again.
        for blob in list(self._bucket.list_blobs(prefix=f"analysis/{video.uid}/{video.id}/")):
            try:
                blob.delete()
            except NotFound:
                pass
        if video.storage_path.startswith(f"videos/{video.uid}/"):
            try:
                self._bucket.blob(video.storage_path).delete()
            except NotFound:
                pass
        ref = self._ref(video.id)
        for name in ("feedback", "interpretations", "analyses"):
            for snap in ref.collection(name).stream():
                snap.reference.delete()
        ref.delete()

    def get_doc(self, collection, doc_id):
        snap = self._db.collection(_training(collection)).document(doc_id).get()
        return snap.to_dict() if snap.exists else None

    def set_doc(self, collection, doc_id, document):
        self._db.collection(_training(collection)).document(doc_id).set(document)

    def delete_doc(self, collection, doc_id):
        self._db.collection(_training(collection)).document(doc_id).delete()

    def list_docs(self, collection, uid):
        query = self._db.collection(_training(collection)).where("uid", "==", uid)
        return [snap.to_dict() for snap in query.stream()]

    def swap_doc(self, collection, doc_id, expected_revision, document):
        ref = self._db.collection(_training(collection)).document(doc_id)

        @self._firestore.transactional
        def run(transaction):
            snap = ref.get(transaction=transaction)
            current = int((snap.to_dict() or {}).get("revision", 0) or 0) if snap.exists else None
            if current != expected_revision:
                return False
            transaction.set(ref, document)
            return True

        return run(self._db.transaction())

    def delete_profile(self, uid):
        self._db.collection("profiles").document(uid).delete()
