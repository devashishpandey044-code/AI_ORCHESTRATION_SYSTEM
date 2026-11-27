import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.db.checkin_models import CheckinOutcomeRow, CheckinRow
from app.db.models import Base
from app.db.plan_models import Plan, PlanBlock, PlanTask
from app.db.session import get_db
from app.main import app

DAY = "2026-11-28"
USER_A = uuid.uuid4()
USER_B = uuid.uuid4()
BODY = {
    "tasks": [
        {"key": "dsa", "title": "DSA practice", "minutes": 120, "priority": 1},
        {"key": "proj", "title": "Project work", "minutes": 45},
        {"key": "read", "title": "Read a paper", "minutes": 30, "priority": 3},
    ],
    "fixed": [{"title": "Lectures", "start": "09:00", "end": "13:00"}],
}


@pytest.fixture
def api():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    models = (Plan, PlanTask, PlanBlock, CheckinRow, CheckinOutcomeRow)
    tables = [m.__table__ for m in models]
    Base.metadata.create_all(engine, tables=tables)
    current = {"user": USER_A}

    def override_db():
        with Session(engine) as db:
            yield db

    def override_user():
        return SimpleNamespace(id=current["user"])

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    client = TestClient(app)
    yield client, current
    app.dependency_overrides.clear()
    engine.dispose()


def path(name):
    return app.url_path_for(name, plan_date=DAY)


def test_routes_exist_under_one_path():
    assert path("build_plan") == path("read_plan") == path("remove_plan")


def test_build_then_read_the_same_plan(api):
    client, _ = api
    built = client.post(path("build_plan"), json=BODY)
    assert built.status_code == 200
    data = built.json()
    assert data["mode"] == "full"
    assert data["blocks"][0]["start"] == "07:00"
    assert any(b["kind"] == "fixed" for b in data["blocks"])
    read = client.get(path("read_plan"))
    assert read.status_code == 200
    assert read.json()["blocks"] == data["blocks"]


def test_low_energy_day_reports_what_was_cut(api):
    client, _ = api
    data = client.post(path("build_plan"), json={**BODY, "low_energy": True}).json()
    assert data["mode"] == "minimum"
    assert [d["key"] for d in data["dropped"]] == ["read"]
    assert {t["key"] for t in data["trimmed"]} == {"dsa", "proj"}


def test_building_again_replaces_the_plan(api):
    client, _ = api
    client.post(path("build_plan"), json=BODY)
    client.post(path("build_plan"), json={**BODY, "low_energy": True})
    assert client.get(path("read_plan")).json()["mode"] == "minimum"


@pytest.mark.parametrize(
    "bad",
    [
        {"tasks": [{"key": "a", "title": "x", "minutes": 5}]},
        {"awake_start": "7am"},
        {"surprise": 1},
    ],
)
def test_bad_requests_get_422(api, bad):
    client, _ = api
    assert client.post(path("build_plan"), json=bad).status_code == 422


def test_bad_date_gets_422(api):
    client, _ = api
    assert client.get(path("read_plan").replace(DAY, "not-a-date")).status_code == 422


def test_missing_plan_is_404(api):
    client, _ = api
    assert client.get(path("read_plan")).status_code == 404
    assert client.delete(path("remove_plan")).status_code == 404


def test_delete_removes_the_plan(api):
    client, _ = api
    client.post(path("build_plan"), json=BODY)
    assert client.delete(path("remove_plan")).status_code == 204
    assert client.get(path("read_plan")).status_code == 404
    assert client.delete(path("remove_plan")).status_code == 404


def test_another_users_plan_is_404_not_403(api):
    client, current = api
    client.post(path("build_plan"), json=BODY)
    current["user"] = USER_B
    assert client.get(path("read_plan")).status_code == 404
    assert client.delete(path("remove_plan")).status_code == 404
    current["user"] = USER_A
    assert client.get(path("read_plan")).status_code == 200


def test_plan_endpoints_need_a_signed_in_user(api):
    client, _ = api
    del app.dependency_overrides[get_current_user]
    assert client.get(path("read_plan")).status_code in (401, 403)
    assert client.post(path("build_plan"), json=BODY).status_code in (401, 403)
