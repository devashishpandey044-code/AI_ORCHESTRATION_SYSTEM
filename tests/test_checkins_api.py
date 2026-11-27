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
PLAN_BODY = {
    "tasks": [
        {"key": "a", "title": "Write", "minutes": 30},
        {"key": "b", "title": "Read", "minutes": 60, "priority": 3},
    ],
    "fixed": [],
}
GOOD = {
    "outcomes": [
        {"task": "a", "status": "done", "actual_minutes": 30},
        {"task": "b", "status": "partial", "actual_minutes": 20, "reason": "interrupted"},
    ],
    "energy": 3,
    "note": "ok day",
}
ALL_DONE = {
    "outcomes": [
        {"task": "a", "status": "done", "actual_minutes": 30},
        {"task": "b", "status": "done", "actual_minutes": 60},
    ]
}
THREE_DAYS = ["2026-11-26", "2026-11-27", "2026-11-28"]


@pytest.fixture
def api():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    models = (Plan, PlanTask, PlanBlock, CheckinRow, CheckinOutcomeRow)
    Base.metadata.create_all(engine, tables=[m.__table__ for m in models])
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


def url(name, plan_date=DAY):
    return app.url_path_for(name, plan_date=plan_date)


def make_plan(client, plan_date=DAY):
    response = client.post(url("build_plan", plan_date), json=PLAN_BODY)
    assert response.status_code == 200
    return response


def fill_days(client, days, body=None):
    for day in days:
        make_plan(client, day)
        response = client.put(url("write_checkin", day), json=body or ALL_DONE)
        assert response.status_code == 200


def test_routes_share_one_path():
    assert url("write_checkin") == url("read_checkin") == url("remove_checkin")
    assert app.url_path_for("weekly_review") == "/reviews/weekly"


def test_put_then_get_returns_the_same_report(api):
    client, _ = api
    make_plan(client)
    put = client.put(url("write_checkin"), json=GOOD)
    assert put.status_code == 200
    data = put.json()
    assert data["date"] == DAY and data["energy"] == 3 and data["note"] == "ok day"
    report = data["report"]
    assert report["planned_minutes"] == 90 and report["counted_minutes"] == 50
    assert report["adherence_percent"] == 56 and report["unreported"] == []
    assert [t["task"] for t in report["tasks"]] == ["a", "b"]
    got = client.get(url("read_checkin"))
    assert got.status_code == 200 and got.json() == data


def test_put_again_replaces(api):
    client, _ = api
    make_plan(client)
    client.put(url("write_checkin"), json=GOOD)
    second = {"outcomes": [{"task": "a", "status": "done", "actual_minutes": 30}]}
    data = client.put(url("write_checkin"), json=second).json()
    assert data["energy"] is None and data["report"]["unreported"] == ["b"]
    assert client.get(url("read_checkin")).json() == data


def test_no_plan_is_404(api):
    client, _ = api
    assert client.put(url("write_checkin"), json=GOOD).status_code == 404


def test_task_that_was_not_planned_is_422(api):
    client, _ = api
    make_plan(client)
    body = {"outcomes": [{"task": "zzz", "status": "done", "actual_minutes": 10}]}
    response = client.put(url("write_checkin"), json=body)
    assert response.status_code == 422
    assert client.get(url("read_checkin")).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"outcomes": [{"task": "a", "status": "skipped", "actual_minutes": 0}]},
        {"outcomes": [{"task": "a", "status": "done", "actual_minutes": 0}]},
        {"outcomes": [{"task": "a", "status": "weird", "actual_minutes": 5}]},
        {"outcomes": [{"task": "a", "status": "done", "actual_minutes": "5"}]},
        {"outcomes": [{"task": "a", "status": "done", "actual_minutes": 5}] * 2},
        {"outcomes": [], "energy": 9},
        {"outcomes": [], "extra": 1},
        {},
    ],
)
def test_bad_bodies_are_422(api, body):
    client, _ = api
    make_plan(client)
    assert client.put(url("write_checkin"), json=body).status_code == 422


def test_bad_date_is_422(api):
    client, _ = api
    assert client.get("/checkins/not-a-date").status_code == 422


def test_get_missing_is_404(api):
    client, _ = api
    make_plan(client)
    assert client.get(url("read_checkin")).status_code == 404


def test_delete(api):
    client, _ = api
    make_plan(client)
    client.put(url("write_checkin"), json=GOOD)
    assert client.delete(url("remove_checkin")).status_code == 204
    assert client.get(url("read_checkin")).status_code == 404
    assert client.delete(url("remove_checkin")).status_code == 404
    assert client.get(url("read_plan")).status_code == 200


def test_another_user_gets_404_not_403(api):
    client, current = api
    make_plan(client)
    client.put(url("write_checkin"), json=GOOD)
    current["user"] = USER_B
    assert client.get(url("read_checkin")).status_code == 404
    assert client.put(url("write_checkin"), json=GOOD).status_code == 404
    assert client.delete(url("remove_checkin")).status_code == 404
    current["user"] = USER_A
    assert client.get(url("read_checkin")).status_code == 200


def test_replanning_the_day_removes_the_checkin(api):
    client, _ = api
    make_plan(client)
    client.put(url("write_checkin"), json=GOOD)
    make_plan(client)
    assert client.get(url("read_checkin")).status_code == 404


def test_weekly_review_needs_a_date(api):
    client, _ = api
    assert client.get("/reviews/weekly").status_code == 422
    assert client.get("/reviews/weekly?end=nope").status_code == 422


def test_weekly_review_with_no_data(api):
    client, _ = api
    data = client.get("/reviews/weekly?end=2026-11-28").json()
    assert data["start"] == "2026-11-22" and data["end"] == "2026-11-28"
    assert data["days_with_checkins"] == 0 and data["adherence_percent"] is None
    assert [s["code"] for s in data["suggestions"]] == ["need_more_data"]


def test_weekly_review_after_three_good_days(api):
    client, _ = api
    fill_days(client, THREE_DAYS)
    data = client.get("/reviews/weekly?end=2026-11-28").json()
    assert data["days_with_checkins"] == 3
    assert data["planned_minutes"] == 270 and data["counted_minutes"] == 270
    assert data["adherence_percent"] == 100 and data["roadblocks"] == []
    assert [s["code"] for s in data["suggestions"]] == ["keep_going"]


def test_weekly_review_finds_a_roadblock(api):
    client, _ = api
    tired = {
        "outcomes": [
            {"task": "a", "status": "done", "actual_minutes": 30},
            {"task": "b", "status": "skipped", "actual_minutes": 0, "reason": "too_tired"},
        ]
    }
    fill_days(client, THREE_DAYS, tired)
    data = client.get("/reviews/weekly?end=2026-11-28").json()
    assert data["roadblocks"][0]["reason"] == "too_tired"
    assert data["roadblocks"][0]["occurrences"] == 3
    assert data["roadblocks"][0]["minutes_lost"] == 180
    codes = [s["code"] for s in data["suggestions"]]
    assert "protect_energy" in codes


def test_weekly_review_window_and_owner(api):
    client, current = api
    fill_days(client, THREE_DAYS)
    assert client.get("/reviews/weekly?end=2026-12-10").json()["days_with_checkins"] == 0
    assert client.get("/reviews/weekly?end=2026-11-26").json()["days_with_checkins"] == 1
    current["user"] = USER_B
    assert client.get("/reviews/weekly?end=2026-11-28").json()["days_with_checkins"] == 0
