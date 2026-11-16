"""Seed labelled SYNTHETIC analysed sessions for one emulator account, for the browser
end-to-end tests of history, comparison and checkpoint follow-up.

    uv run python scripts/e2e_seed.py <uid>

Emulator only: it refuses to run unless the Firestore and Storage emulator hosts are set and
the project is the demo project. The sessions come from the synthetic swimmer used by the
unit tests, with edited values, and their file names say SYNTHETIC. They are test fixtures,
never anyone's swimming and never evidence of progress.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8080")
os.environ.setdefault("STORAGE_EMULATOR_HOST", "http://127.0.0.1:9199")
os.environ.setdefault("FIREBASE_AUTH_EMULATOR_HOST", "127.0.0.1:9099")


def main(uid: str) -> None:
    from aquatrack.api import config

    problems = config.validate("api")
    if config.environment() != "emulator" or problems:
        raise SystemExit(
            "e2e_seed.py only runs against the Firebase emulators: " + "; ".join(problems)
        )
    from test_history import session  # the unit tests' labelled synthetic sessions
    from test_interpretation import EVEN

    from aquatrack.api import jobs
    from aquatrack.api.store import FirebaseStore

    store = FirebaseStore()
    fast = [0.8, 0.8, 0.84, 0.8, 0.76, 0.8, 0.8]  # 75 cycles/min: a clearly different effort
    plan = [
        ("synthetic-1", 1, {"distance": "100 m"}, {"leg_line_angle": 0.0}, EVEN),
        ("synthetic-2", 8, {"distance": "100 m"}, {"leg_line_angle": 10.0}, EVEN),
        ("synthetic-sprint", 15, {"distance": "100 m"}, {}, fast),
    ]
    for vid, day, fields, edit, times in plan:
        s = session(vid, day, times=times, edit=edit, **fields)
        video_id = f"{vid}-{uid[:6]}"
        store._db.collection("videos").document(video_id).set(
            {
                "uid": uid,
                "status": "analyzing",
                "storagePath": f"videos/{uid}/{video_id}.mp4",  # no file: a fixture record
                "contentType": "video/mp4",
                "fileName": f"SYNTHETIC test session {day}.mp4",
                "stroke": "Freestyle",
                "camera": "Underwater",
                "distance": "100 m",
                "createdAt": datetime.fromisoformat(s.recorded_at),
                "synthetic": True,
            }
        )
        video = store.get_video(video_id)
        result = s.result.model_copy(update={"video_id": video_id})
        store.save_analysis(video, "a1", result.to_firestore(), {})
        store.update_video(video_id, {"status": "ready", "latestAnalysisId": "a1"})
        jobs.interpret_video(store, store.get_video(video_id), "a1")
        print("seeded", video_id)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
