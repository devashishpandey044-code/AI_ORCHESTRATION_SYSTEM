import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings
from tests.conftest import PASSWORD


def _register(client, email="alice@example.com", **overrides):
    body = {"email": email, "password": PASSWORD, "consent": True} | overrides
    return client.post("/auth/register", json=body)


def test_register_success_hides_password(client):
    r = _register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "alice@example.com"
    assert "password" not in body and "password_hash" not in body
    assert body["consent_at"]


def test_register_requires_consent(client):
    assert _register(client, consent=False).status_code == 422


def test_register_rejects_short_password(client):
    assert _register(client, password="short").status_code == 422


def test_register_rejects_invalid_email(client):
    assert _register(client, email="not-an-email").status_code == 422


def test_duplicate_email_conflict_is_case_insensitive(client):
    assert _register(client, "alice@example.com").status_code == 201
    assert _register(client, "Alice@Example.com").status_code == 409


def test_login_success_and_case_insensitive_email(client):
    _register(client, "alice@example.com")
    r = client.post("/auth/login", json={"email": "ALICE@example.com", "password": PASSWORD})
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"
    assert r.json()["access_token"]


def test_login_wrong_password(client):
    _register(client)
    r = client.post("/auth/login", json={"email": "alice@example.com", "password": "wrong-password"})
    assert r.status_code == 401


def test_login_unknown_email(client):
    r = client.post("/auth/login", json={"email": "ghost@example.com", "password": PASSWORD})
    assert r.status_code == 401


def test_me_requires_token(client):
    assert client.get("/auth/me").status_code == 401


def test_me_returns_current_user(client, auth):
    r = client.get("/auth/me", headers=auth)
    assert r.status_code == 200
    assert r.json()["email"] == "alice@example.com"


def test_invalid_token_rejected(client):
    r = client.get("/auth/me", headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401


def test_expired_token_rejected(client):
    settings = get_settings()
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "exp": datetime.now(UTC) - timedelta(minutes=1)},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_token_for_nonexistent_user_rejected(client):
    settings = get_settings()
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "exp": datetime.now(UTC) + timedelta(minutes=5)},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
