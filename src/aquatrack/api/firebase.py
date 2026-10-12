"""Firebase login for API routes.

The web app signs people in with Firebase Authentication and sends their ID token as
`Authorization: Bearer <token>`. Routes that need a user depend on `current_user`.
"""

from dataclasses import dataclass
from functools import cache
from typing import Annotated

import firebase_admin
from fastapi import Depends, Header, HTTPException, status
from firebase_admin import auth, credentials

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
    options = {"projectId": FIREBASE_PROJECT_ID} if FIREBASE_PROJECT_ID else None
    return firebase_admin.initialize_app(cred, options)


def verify_token(token: str) -> dict:
    return auth.verify_id_token(token, app=_app())


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
    return FirebaseUser(uid=claims["uid"], email=claims.get("email"), name=claims.get("name"))


CurrentUser = Annotated[FirebaseUser, Depends(current_user)]
