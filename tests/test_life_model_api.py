import pytest
from sqlalchemy import text

from app.services import life_model as lm

V1 = {
    "current_situation": "Student",
    "vision": [{"text": "Become a developer", "provenance": "stated", "evidence": "developer"}],
}


def _seed(client, auth, data=None):
    r = client.post("/onboarding/confirm", json={"data": data or V1}, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


def _edit(client, auth, data):
    return client.put("/life-model", json={"data": data}, headers=auth)


def _count(engine, table):
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()


# ---- edit ------------------------------------------------------------------

def test_edit_requires_auth(client):
    assert client.put("/life-model", json={"data": {}}).status_code == 401


def test_edit_without_a_model_returns_404(client, auth):
    assert _edit(client, auth, {"current_situation": "x"}).status_code == 404


def test_edit_creates_a_new_user_edit_version(client, auth):
    _seed(client, auth)
    r = _edit(client, auth, {"current_situation": "Graduate"})
    assert r.status_code == 200
    assert r.json()["version"] == 2
    assert r.json()["source"] == "user_edit"
    current = client.get("/life-model", headers=auth).json()
    assert current["data"]["current_situation"] == "Graduate"


def test_identical_edit_creates_no_new_version(client, auth):
    _seed(client, auth)
    r = _edit(client, auth, V1)
    assert r.status_code == 200
    assert r.json()["version"] == 1
    assert len(client.get("/life-model/versions", headers=auth).json()) == 1


def test_edit_can_clear_everything(client, auth):
    _seed(client, auth)
    r = _edit(client, auth, {})
    assert r.status_code == 200
    assert r.json()["version"] == 2
    assert r.json()["data"]["vision"] == []


def test_edit_rejects_unknown_fields(client, auth):
    _seed(client, auth)
    assert _edit(client, auth, {"hobbies": []}).status_code == 422


def test_edit_and_restore_never_call_the_model(client, engine, auth):
    _seed(client, auth)
    _edit(client, auth, {"current_situation": "Graduate"})
    client.post("/life-model/versions/1/restore", headers=auth)
    assert _count(engine, "llm_calls") == 0


def test_edit_conflict_returns_409(client, auth, monkeypatch):
    _seed(client, auth)

    def boom(*args, **kwargs):
        raise lm.VersionConflictError

    monkeypatch.setattr(lm, "save_new_version", boom)
    assert _edit(client, auth, {"current_situation": "X"}).status_code == 409


def test_confirm_conflict_returns_409(client, auth, monkeypatch):
    def boom(*args, **kwargs):
        raise lm.VersionConflictError

    monkeypatch.setattr(lm, "save_new_version", boom)
    r = client.post("/onboarding/confirm", json={"data": V1}, headers=auth)
    assert r.status_code == 409


# ---- history ---------------------------------------------------------------

def test_list_versions_newest_first_without_data(client, auth):
    _seed(client, auth)
    _edit(client, auth, {"current_situation": "A"})
    _edit(client, auth, {"current_situation": "B"})
    versions = client.get("/life-model/versions", headers=auth).json()
    assert [v["version"] for v in versions] == [3, 2, 1]
    assert [v["source"] for v in versions] == ["user_edit", "user_edit", "onboarding"]
    assert "data" not in versions[0]


def test_list_versions_is_private(client, auth, other_auth):
    _seed(client, auth)
    assert client.get("/life-model/versions", headers=other_auth).json() == []


def test_get_specific_version(client, auth):
    _seed(client, auth)
    _edit(client, auth, {"current_situation": "Graduate"})
    old = client.get("/life-model/versions/1", headers=auth).json()
    assert old["data"]["current_situation"] == "Student"
    assert old["source"] == "onboarding"


def test_get_missing_version_returns_404(client, auth):
    _seed(client, auth)
    assert client.get("/life-model/versions/9", headers=auth).status_code == 404


def test_get_version_of_another_user_returns_404(client, auth, other_auth):
    _seed(client, auth)
    assert client.get("/life-model/versions/1", headers=other_auth).status_code == 404


@pytest.mark.parametrize("number", [0, -1, 1_000_001])
def test_version_number_bounds(client, auth, number):
    assert client.get(f"/life-model/versions/{number}", headers=auth).status_code == 422


# ---- restore ---------------------------------------------------------------

def test_restore_creates_a_new_version_and_keeps_history(client, auth):
    _seed(client, auth)
    _edit(client, auth, {"current_situation": "Graduate"})
    r = client.post("/life-model/versions/1/restore", headers=auth)
    assert r.status_code == 201
    assert r.json()["version"] == 3
    assert r.json()["data"]["current_situation"] == "Student"
    assert len(client.get("/life-model/versions", headers=auth).json()) == 3
    kept = client.get("/life-model/versions/2", headers=auth).json()
    assert kept["data"]["current_situation"] == "Graduate"


def test_restore_current_version_is_a_conflict(client, auth):
    _seed(client, auth)
    assert client.post("/life-model/versions/1/restore", headers=auth).status_code == 409


def test_restore_missing_version_returns_404(client, auth):
    _seed(client, auth)
    assert client.post("/life-model/versions/7/restore", headers=auth).status_code == 404


def test_restore_another_users_version_returns_404(client, auth, other_auth):
    _seed(client, auth)
    assert client.post("/life-model/versions/1/restore", headers=other_auth).status_code == 404


def test_history_endpoints_require_auth(client):
    assert client.get("/life-model/versions").status_code == 401
    assert client.get("/life-model/versions/1").status_code == 401
    assert client.post("/life-model/versions/1/restore").status_code == 401
