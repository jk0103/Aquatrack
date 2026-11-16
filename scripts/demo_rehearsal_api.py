"""Run the API for a LOCAL rehearsal of the account-restricted demonstration.

Same switches as the hosted demo (restricted access, demo mode, saved pose data) but in the
emulator environment: no real project, no credentials. The allowed accounts are read from
.demo-rehearsal-uids (untracked), written by scripts/demo_rehearsal_accounts.py.

    uv run python scripts/demo_rehearsal_api.py
"""

import os
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    uids = ROOT / ".demo-rehearsal-uids"
    # An empty folder: the pose file must come from the (emulated) bucket, as when hosted.
    pose_dir = Path(tempfile.gettempdir()) / "aquatrack-demo-rehearsal-pose"
    shutil.rmtree(pose_dir, ignore_errors=True)
    os.environ.update(
        AQUATRACK_ENV="emulator",
        FIREBASE_AUTH_EMULATOR_HOST="127.0.0.1:9099",
        FIRESTORE_EMULATOR_HOST="127.0.0.1:8080",
        STORAGE_EMULATOR_HOST="http://127.0.0.1:9199",
        FIREBASE_PROJECT_ID="demo-aquatrack",
        AQUATRACK_ACCESS="restricted",
        AQUATRACK_DEMO="1",
        AQUATRACK_POSE_SOURCE="precomputed",
        AQUATRACK_PRECOMPUTED_POSE_DIR=str(pose_dir),
        AQUATRACK_ALLOWED_UIDS=",".join(uids.read_text().split()) if uids.is_file() else "",
    )
    for name in ("GOOGLE_APPLICATION_CREDENTIALS", "AQUATRACK_ALLOW_PRODUCTION_FIREBASE"):
        os.environ.pop(name, None)
    import uvicorn

    uvicorn.run("aquatrack.api.main:app", port=8000, log_level="info")


if __name__ == "__main__":
    main()
