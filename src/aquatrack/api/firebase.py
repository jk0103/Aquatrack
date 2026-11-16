"""Firebase login for API routes.

The web app signs people in with Firebase Authentication and sends their ID token as
`Authorization: Bearer <token>`. Routes that need a user depend on `current_user`.
"""

import os
from dataclasses import dataclass
from functools import cache
from typing import Annotated

import firebase_admin
from fastapi import Depends, Header, HTTPException, status
from firebase_admin import auth, credentials

from aquatrack.api import config
from aquatrack.api.config import FIREBASE_CREDENTIALS, FIREBASE_PROJECT_ID


@dataclass(frozen=True)
class FirebaseUser:
    uid: str
    email: str | None
    name: str | None


@cache
def _app() -> firebase_admin.App:
    # With a service account key the backend can also read Firestore and Storage.
    # Verifying logins only needs the project id. When FIREBASE_AUTH_EMULATOR_HOST is set,
    # tokens from the local emulator are accepted instead.
    cred = credentials.Certificate(FIREBASE_CREDENTIALS) if FIREBASE_CREDENTIALS else None
    project = FIREBASE_PROJECT_ID
    if not project and os.environ.get("FIREBASE_AUTH_EMULATOR_HOST"):
        project = "demo-aquatrack"  # the emulator project; never a real one
    options = {"projectId": project} if project else None
    return firebase_admin.initialize_app(cred, options)


def verify_token(token: str) -> dict:
    return auth.verify_id_token(token, app=_app())


def delete_auth_user(uid: str) -> None:
    """Remove the sign-in itself. A user that is already gone is fine."""
    try:
        auth.delete_user(uid, app=_app())
    except auth.UserNotFoundError:
        pass


def current_user(authorization: Annotated[str | None, Header()] = None) -> FirebaseUser:
    """Dependency for routes that need a logged-in user."""
    not_logged_in = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise not_logged_in
    try:
        claims = verify_token(token)
    except (ValueError, auth.InvalidIdTokenError, auth.ExpiredIdTokenError):
        raise not_logged_in from None
    if not config.is_allowed(claims["uid"]):
        # Signed in, but not one of the accounts this deployment was opened to. Checked
        # here, on every route that needs a user, never only in the web app.
        raise HTTPException(status.HTTP_403_FORBIDDEN, config.ACCESS_DENIED)
    return FirebaseUser(uid=claims["uid"], email=claims.get("email"), name=claims.get("name"))


def sync_access_claims(allowed: frozenset[str]) -> dict[str, int]:
    """Make the custom claim the restricted security rules look for match the allowed
    accounts: set on every listed account that exists, removed from every other account
    (whose sessions are then ended). Creates no account. Returns counts only."""
    counts = {"granted": 0, "revoked": 0, "missing": 0}
    seen: set[str] = set()
    for user in auth.list_users(app=_app()).iterate_all():
        claims = dict(user.custom_claims or {})
        has = claims.get(config.ACCESS_CLAIM) is True
        if user.uid in allowed:
            seen.add(user.uid)
            if not has:
                claims[config.ACCESS_CLAIM] = True
                auth.set_custom_user_claims(user.uid, claims, app=_app())
                counts["granted"] += 1
        elif has:
            claims.pop(config.ACCESS_CLAIM)
            auth.set_custom_user_claims(user.uid, claims or None, app=_app())
            auth.revoke_refresh_tokens(user.uid, app=_app())
            counts["revoked"] += 1
    counts["missing"] = len(allowed - seen)
    return counts


CurrentUser = Annotated[FirebaseUser, Depends(current_user)]
