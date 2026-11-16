"""Deleting a whole account, and refusing new work while that is happening.

Order: a marker first (from then on nothing new can be started or written for the account),
then every video with everything derived from it, then training data, then the profile,
then the sign-in itself, and the marker last. Every step tolerates data that is already
gone, so the same request finishes a deletion that stopped part way. Storage paths and
internals never appear in an answer.

This has been run against the Firebase emulators with disposable accounts only. What a
production deletion additionally needs (backups, logs, a queue that finishes the job when
the user never comes back, legal review) is listed in docs/DATA_LIFECYCLE.md.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from aquatrack.api import jobs
from aquatrack.api.store import Store

log = logging.getLogger("aquatrack.account")

MARKERS = "account_deletions"
OWNED = ("training_sessions", "training_plans", "training_state")
CONFIRM_PHRASE = "DELETE MY ACCOUNT"


class AccountError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def is_deleting(store: Store, uid: str) -> bool:
    return store.get_doc(MARKERS, uid) is not None


def guard(store: Store, uid: str) -> None:
    """Called before anything that starts work or writes data for the account."""
    if is_deleting(store, uid):
        raise AccountError(409, "This account is being deleted.")


def delete_account(
    store: Store, uid: str, confirm: object, delete_sign_in: Callable[[str], None]
) -> dict:
    """Delete everything the account owns, then the account. Needs the exact confirmation
    phrase. Safe to call again after a failure."""
    if confirm != CONFIRM_PHRASE:
        raise AccountError(422, f'Type "{CONFIRM_PHRASE}" to confirm.')
    already = store.get_doc(MARKERS, uid)
    if already is None:
        store.set_doc(
            MARKERS,
            uid,
            {"uid": uid, "id": uid, "requestedAt": datetime.now(UTC).isoformat(timespec="seconds")},
        )
    counts = {"videos": 0, "training": 0}
    try:
        for video in store.list_videos(uid):
            # delete_video stops any running analysis from storing results first.
            jobs.delete_video(store, video.id, uid)
            counts["videos"] += 1
        for collection in OWNED:
            for doc in store.list_docs(collection, uid):
                store.delete_doc(collection, str(doc["id"]))
                counts["training"] += 1
        store.delete_profile(uid)
        delete_sign_in(uid)
        store.delete_doc(MARKERS, uid)
    except Exception:
        log.exception("account deletion incomplete")  # no uid, no paths in the log line
        raise AccountError(
            503,
            "Some of your data could not be deleted yet. Nothing new will be added to "
            "your account; try again to finish deleting it.",
        ) from None
    return {"deleted": True, "resumed": already is not None, **counts}
