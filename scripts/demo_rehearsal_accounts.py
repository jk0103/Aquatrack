"""Set up a LOCAL rehearsal of the account-restricted demonstration in the Firebase emulators.

Emulator only: it refuses to run unless the emulator hosts are set, and it never touches a
real project. It creates two throwaway emulator accounts with random passwords:

  invited   listed in .demo-rehearsal-uids, which scripts/demo_rehearsal_api.py reads
  stranger  signed up but not listed: must be refused everywhere

and copies the saved pose file of the approved test video into the emulated bucket, where
the demo backend looks for it. Sign-in details go to frontend/.env.demo-rehearsal.local
(untracked); nothing is printed.

    uv run python scripts/demo_rehearsal_accounts.py

For the real demonstration project the owner creates the accounts in the Firebase console;
this script is not used there.
"""

import os
import secrets
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "demo-aquatrack"
BUCKET = f"{PROJECT}.appspot.com"
APPROVED_SHA256 = "ce32d556ba1399b9dd5000f9a079475ca33377a9280cf30619a566ff8e9523c3"
POSE = ROOT / "data/precomputed_pose" / f"{APPROVED_SHA256}.rawpose.npz"


def sign_up(auth: str, label: str) -> tuple[str, str, str]:
    email = f"demo-{label}-{secrets.token_hex(3)}@example.test"
    password = secrets.token_urlsafe(12)
    res = httpx.post(
        f"{auth}/accounts:signUp?key=demo-key",
        json={"email": email, "password": password, "returnSecureToken": True},
    )
    res.raise_for_status()
    return res.json()["localId"], email, password


def main() -> int:
    auth_host = os.environ.get("FIREBASE_AUTH_EMULATOR_HOST", "127.0.0.1:9099")
    storage_host = os.environ.get("STORAGE_EMULATOR_HOST", "http://127.0.0.1:9199")
    if not all(
        h.split("//")[-1].startswith(("127.0.0.1", "localhost")) for h in (auth_host, storage_host)
    ):
        print("This script only works against local emulators.", file=sys.stderr)
        return 2
    if not POSE.is_file():
        print(f"Missing {POSE.relative_to(ROOT)} (the saved pose file).", file=sys.stderr)
        return 2
    auth = f"http://{auth_host}/identitytoolkit.googleapis.com/v1"
    invited = sign_up(auth, "invited")
    stranger = sign_up(auth, "stranger")
    (ROOT / ".demo-rehearsal-uids").write_text(invited[0] + "\n")
    (ROOT / "frontend/.env.demo-rehearsal.local").write_text(
        "# Local Firebase EMULATOR rehearsal accounts only (not real accounts). Untracked.\n"
        f"DEMO_INVITED_EMAIL={invited[1]}\nDEMO_INVITED_PASSWORD={invited[2]}\n"
        f"DEMO_STRANGER_EMAIL={stranger[1]}\nDEMO_STRANGER_PASSWORD={stranger[2]}\n"
    )
    name = f"demo_fixtures/pose/{POSE.name}".replace("/", "%2F")
    res = httpx.post(
        f"{storage_host}/v0/b/{BUCKET}/o?name={name}",
        headers={"Authorization": "Bearer owner", "Content-Type": "application/octet-stream"},
        content=POSE.read_bytes(),
    )
    res.raise_for_status()
    print("Rehearsal accounts created; pose file stored in the emulated bucket.")
    print("Start the API with scripts/demo_rehearsal_api.py (restart it if it was running).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
