import pytest
from fastapi.testclient import TestClient
from firebase_admin import auth

from aquatrack.api import firebase
from aquatrack.api.main import app

CLAIMS = {"uid": "swimmer-1", "email": "alice@example.com", "name": "Alice"}


@pytest.fixture
def client(monkeypatch):
    def fake_verify(token: str) -> dict:
        if token == "good-token":
            return CLAIMS
        raise auth.InvalidIdTokenError("bad token")

    monkeypatch.setattr(firebase, "verify_token", fake_verify)
    return TestClient(app)


def test_me_with_valid_token(client):
    res = client.get("/me", headers={"Authorization": "Bearer good-token"})
    assert res.status_code == 200
    assert res.json() == {"uid": "swimmer-1", "email": "alice@example.com", "name": "Alice"}


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer bad-token"},
        {"Authorization": "Basic good-token"},
        {"Authorization": "Bearer"},
    ],
)
def test_me_rejects_missing_or_bad_tokens(client, headers):
    assert client.get("/me", headers=headers).status_code == 401
