"""Where videos, job state and analysis results live.

`FirebaseStore` talks to Firestore and Storage with admin rights (the web app's security
rules do not let clients write job state or results). `MemoryStore` is the same interface
in memory, for tests.

Firestore layout:
  videos/{id}                      the upload record; the backend adds `status`, `job`,
                                   `latestAnalysisId` and a small `analysisSummary`
  videos/{id}/analyses/{analysisId}  one AnalysisResult (structured, no per-frame arrays)
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

from aquatrack.api.config import FIREBASE_PROJECT_ID
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


def _record(video_id: str, data: dict[str, Any]) -> VideoRecord:
    return VideoRecord(
        id=video_id,
        uid=str(data.get("uid", "")),
        storage_path=str(data.get("storagePath", "")),
        status=str(data.get("status", "uploaded")),
        content_type=str(data.get("contentType", "")),
        size_bytes=int(data.get("sizeBytes", 0) or 0),
        job=dict(data.get("job") or {}),
        session=SessionInfo(
            stroke=str(data.get("stroke", "")),
            camera=str(data.get("camera", "")),
            distance=str(data.get("distance", "")),
            pool_length=str(data.get("poolLength", "")),
        ),
    )


def artifact_path(video: VideoRecord, analysis_id: str, name: str) -> str:
    return f"analysis/{video.uid}/{video.id}/{analysis_id}/{name}"


def _document(video: VideoRecord, result: dict, saved: dict[str, tuple[str, int]]) -> dict:
    """The analysis document: the result, its owner, and where the big arrays are."""
    artifacts = [
        {"kind": Path(name).stem, "storage_path": path, "bytes": size}
        for name, (path, size) in saved.items()
    ]
    return {**result, "uid": video.uid, "artifacts": artifacts}


class MemoryStore:
    """In-memory Store for tests. `videos` maps id -> Firestore-style document dict."""

    def __init__(self):
        self.videos: dict[str, dict[str, Any]] = {}
        self.files: dict[str, bytes] = {}
        self.analyses: dict[tuple[str, str], dict[str, Any]] = {}
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
        if not emulated and os.environ.get("AQUATRACK_ALLOW_PRODUCTION_FIREBASE") != "1":
            raise RuntimeError(
                "Firebase emulators are not configured (FIRESTORE_EMULATOR_HOST and "
                "STORAGE_EMULATOR_HOST). Production Firebase is not enabled for this project."
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
        self._ref(video_id).set(fields, merge=True)

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
