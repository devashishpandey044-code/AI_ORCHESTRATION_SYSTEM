import pytest

from app.core.config import get_settings

PASSWORD = "a-long-enough-password"


def register(client, email):
    return client.post(
        "/auth/register", json={"email": email, "password": PASSWORD, "consent": True}
    )


@pytest.fixture
def cap(monkeypatch):
    def set_cap(limit: int) -> None:
        patched = get_settings().model_copy(update={"max_users": limit})
        monkeypatch.setattr("app.api.auth.get_settings", lambda: patched)

    return set_cap


def test_signups_stop_once_the_cap_is_reached(client, cap):
    cap(2)
    assert register(client, "a@example.com").status_code == 201
    assert register(client, "b@example.com").status_code == 201
    full = register(client, "c@example.com")
    assert full.status_code == 403
    assert "full" in full.json()["detail"]


def test_an_existing_email_still_gets_the_normal_answer_when_full(client, cap):
    cap(1)
    assert register(client, "a@example.com").status_code == 201
    assert register(client, "a@example.com").status_code == 409


def test_people_with_an_account_can_still_sign_in_when_full(client, cap):
    cap(1)
    register(client, "a@example.com")
    login = client.post("/auth/login", json={"email": "a@example.com", "password": PASSWORD})
    assert login.status_code == 200
    assert register(client, "z@example.com").status_code == 403


def test_zero_means_no_limit(client, cap):
    cap(0)
    for index in range(4):
        assert register(client, f"user{index}@example.com").status_code == 201


def test_a_refused_signup_creates_nothing(client, cap):
    cap(1)
    register(client, "a@example.com")
    register(client, "b@example.com")
    login = client.post("/auth/login", json={"email": "b@example.com", "password": PASSWORD})
    assert login.status_code == 401
