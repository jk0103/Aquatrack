import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from aquatrack.api import models  # noqa: F401  registers the tables
from aquatrack.api.auth import COOKIE_NAME
from aquatrack.api.db import get_session
from aquatrack.api.main import app

ALICE = {"name": "Alice", "email": "alice@example.com", "password": "freestyle50"}


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)

    def session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_signup_logs_you_in(client):
    res = client.post("/auth/signup", json=ALICE)
    assert res.status_code == 201
    assert res.json() == {"id": 1, "name": "Alice", "email": "alice@example.com"}
    assert "httponly" in res.headers["set-cookie"].lower()
    assert client.get("/auth/me").json()["email"] == "alice@example.com"


def test_signup_never_returns_password(client):
    body = client.post("/auth/signup", json=ALICE).json()
    assert "password" not in body and "password_hash" not in body


def test_signup_duplicate_email_is_case_insensitive(client):
    client.post("/auth/signup", json=ALICE)
    res = client.post("/auth/signup", json={**ALICE, "email": "ALICE@example.com"})
    assert res.status_code == 409


@pytest.mark.parametrize(
    "change",
    [{"password": "short"}, {"email": "not-an-email"}, {"name": "   "}],
)
def test_signup_validation(client, change):
    assert client.post("/auth/signup", json={**ALICE, **change}).status_code == 422


def test_login(client):
    client.post("/auth/signup", json=ALICE)
    client.cookies.clear()
    assert client.get("/auth/me").status_code == 401

    res = client.post("/auth/login", json={"email": "Alice@Example.com", "password": "freestyle50"})
    assert res.status_code == 200
    assert client.get("/auth/me").json()["name"] == "Alice"


@pytest.mark.parametrize(
    "creds",
    [
        {"email": "alice@example.com", "password": "wrong-password"},
        {"email": "nobody@example.com", "password": "freestyle50"},
    ],
)
def test_login_rejects_bad_credentials(client, creds):
    client.post("/auth/signup", json=ALICE)
    client.cookies.clear()
    res = client.post("/auth/login", json=creds)
    assert res.status_code == 401
    assert res.json()["detail"] == "Incorrect email or password"


def test_logout(client):
    client.post("/auth/signup", json=ALICE)
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401


def test_tampered_cookie_is_rejected(client):
    client.cookies.set(COOKIE_NAME, "not-a-real-token")
    assert client.get("/auth/me").status_code == 401
