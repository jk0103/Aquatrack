"""Accounts: sign up, log in, log out, and who is logged in.

Sessions are a signed token in an httpOnly cookie, so page scripts can never read it.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pwdlib import PasswordHash
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from aquatrack.api.config import COOKIE_SECURE, SECRET_KEY, SESSION_DAYS
from aquatrack.api.db import get_session
from aquatrack.api.models import User

COOKIE_NAME = "aquatrack_session"
_ALGORITHM = "HS256"

password_hasher = PasswordHash.recommended()
# Checked against when the email is unknown, so a wrong email takes as long as a wrong password.
_DUMMY_HASH = password_hasher.hash("not-a-real-password")

router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[Session, Depends(get_session)]


class SignupRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class UserOut(BaseModel):
    id: int
    name: str
    email: str


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _start_session(response: Response, user: User) -> None:
    expires = datetime.now(UTC) + timedelta(days=SESSION_DAYS)
    token = jwt.encode({"sub": str(user.id), "exp": expires}, SECRET_KEY, algorithm=_ALGORITHM)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_DAYS * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
    )


def current_user(
    session: SessionDep,
    token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> User:
    """Dependency for routes that need a logged-in user."""
    not_logged_in = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    if not token:
        raise not_logged_in
    try:
        user_id = int(jwt.decode(token, SECRET_KEY, algorithms=[_ALGORITHM])["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise not_logged_in from None
    user = session.get(User, user_id)
    if user is None:
        raise not_logged_in
    return user


@router.post("/signup", status_code=status.HTTP_201_CREATED, response_model=UserOut)
def signup(body: SignupRequest, response: Response, session: SessionDep) -> User:
    email = _normalize_email(body.email)
    if session.exec(select(User).where(User.email == email)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(email=email, name=body.name, password_hash=password_hasher.hash(body.password))
    session.add(user)
    try:
        session.commit()
    except IntegrityError:  # two signups with the same email at once
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "An account with this email already exists"
        ) from None
    session.refresh(user)
    _start_session(response, user)
    return user


@router.post("/login", response_model=UserOut)
def login(body: LoginRequest, response: Response, session: SessionDep) -> User:
    user = session.exec(select(User).where(User.email == _normalize_email(body.email))).first()
    valid = password_hasher.verify(body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not valid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    _start_session(response, user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, httponly=True, samesite="lax", secure=COOKIE_SECURE)


@router.get("/me", response_model=UserOut)
def me(user: Annotated[User, Depends(current_user)]) -> User:
    return user
