"""FastAPI app. Run locally with: uv run uvicorn aquatrack.api.main:app --reload"""

import os
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile

from aquatrack import __version__
from aquatrack.analysis.video import read_video_info
from aquatrack.api.firebase import CurrentUser

UPLOAD_DIR = Path(os.environ.get("AQUATRACK_UPLOAD_DIR", "data/uploads"))
ALLOWED_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv"}


app = FastAPI(title="Aquatrack", version=__version__)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/me")
def me(user: CurrentUser) -> dict:
    """Who the Firebase ID token belongs to."""
    return {"uid": user.uid, "email": user.email, "name": user.name}


@app.post("/videos")
def upload_video(file: UploadFile) -> dict:
    """Store an uploaded swim video and return its basic properties."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(400, f"Unsupported video type {suffix!r}")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    video_id = uuid.uuid4().hex
    dest = UPLOAD_DIR / f"{video_id}{suffix}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    try:
        info = read_video_info(dest)
    except ValueError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "File is not a readable video") from e

    return {
        "id": video_id,
        "width": info.width,
        "height": info.height,
        "fps": info.fps,
        "frame_count": info.frame_count,
        "duration_s": round(info.duration_s, 2),
    }
