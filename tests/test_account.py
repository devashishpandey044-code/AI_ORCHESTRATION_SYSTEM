from sqlalchemy import text

from tests.conftest import PASSWORD


def _count(engine, table):
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()


def _seed(client, auth):
    vision = client.post(
        "/goals", json={"title": "Vision", "horizon": "vision"}, headers=auth
    ).json()
    client.post(
        "/goals",
        json={"title": "M", "horizon": "milestone", "parent_id": vision["id"]},
        headers=auth,
    )
    client.post(
        "/constraints",
        json={
            "title": "Class",
            "kind": "fixed_commitment",
            "days_of_week": [0],
            "start_time": "09:00",
            "end_time": "10:00",
        },
        headers=auth,
    )


def test_export_requires_auth(client):
    assert client.get("/auth/me/export").status_code == 401


def test_export_contains_own_data_only(client, auth, other_auth):
    _seed(client, auth)
    client.post("/goals", json={"title": "Bobs", "horizon": "vision"}, headers=other_auth)

    r = client.get("/auth/me/export", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == "alice@example.com"
    assert sorted(g["title"] for g in body["goals"]) == ["M", "Vision"]
    assert [c["title"] for c in body["constraints"]] == ["Class"]
    assert body["exported_at"]


def test_export_never_includes_password(client, auth):
    raw = client.get("/auth/me/export", headers=auth).text
    assert "password" not in raw


def test_delete_requires_auth(client):
    assert client.delete("/auth/me").status_code == 401


def test_delete_account_removes_user_and_all_data(client, engine, auth, other_auth):
    _seed(client, auth)
    client.post("/goals", json={"title": "Bobs", "horizon": "vision"}, headers=other_auth)

    assert client.delete("/auth/me", headers=auth).status_code == 204

    assert client.get("/auth/me", headers=auth).status_code == 401
    login = client.post(
        "/auth/login", json={"email": "alice@example.com", "password": PASSWORD}
    )
    assert login.status_code == 401
    assert _count(engine, "users") == 1  # only Bob remains
    assert _count(engine, "goals") == 1  # only Bob's goal
    assert _count(engine, "schedule_constraints") == 0


def test_deleted_email_can_register_again(client, auth):
    assert client.delete("/auth/me", headers=auth).status_code == 204
    r = client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": PASSWORD, "consent": True},
    )
    assert r.status_code == 201


def test_delete_does_not_touch_other_users(client, auth, other_auth):
    _seed(client, other_auth)
    client.delete("/auth/me", headers=auth)
    assert len(client.get("/goals", headers=other_auth).json()) == 2
    assert len(client.get("/constraints", headers=other_auth).json()) == 1
