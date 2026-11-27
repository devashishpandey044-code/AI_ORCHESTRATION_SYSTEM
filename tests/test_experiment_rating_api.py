import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.db.checkin_models import CheckinOutcomeRow, CheckinRow
from app.db.models import Base, ExperimentStatus, MethodExperiment
from app.db.plan_models import Plan, PlanBlock, PlanTask
from app.db.session import get_db
from app.main import app

USER_A = uuid.uuid4()
USER_B = uuid.uuid4()
PLAN_BODY = {"tasks": [{"key": "a", "title": "Write", "minutes": 100}], "fixed": []}
DONE = {"outcomes": [{"task": "a", "status": "done", "actual_minutes": 100}]}
MISSED = {"outcomes": [{"task": "a", "status": "skipped", "actual_minutes": 0, "reason": "other"}]}
STARTED = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
DURING = ["2026-11-23", "2026-11-24", "2026-11-25"]
BEFORE = ["2026-11-18", "2026-11-19", "2026-11-20"]


@pytest.fixture
def api():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    models = (Plan, PlanTask, PlanBlock, CheckinRow, CheckinOutcomeRow, MethodExperiment)
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
    yield client, current, engine
    app.dependency_overrides.clear()
    engine.dispose()


def add_experiment(engine, user=USER_A, ended_at=None):
    experiment_id = uuid.uuid4()
    with Session(engine) as db:
        db.add(
            MethodExperiment(
                id=experiment_id,
                user_id=user,
                method_slug="some_method",
                roadblock="other",
                status=list(ExperimentStatus)[0],
                started_at=STARTED,
                ended_at=ended_at,
            )
        )
        db.commit()
    return experiment_id


def fill(client, days, body):
    for day in days:
        built = client.post(app.url_path_for("build_plan", plan_date=day), json=PLAN_BODY)
        assert built.status_code == 200
        put = client.put(app.url_path_for("write_checkin", plan_date=day), json=body)
        assert put.status_code == 200


def suggest(client, experiment_id, query=""):
    return client.get(f"/methods/experiments/{experiment_id}/suggested-rating{query}")


def test_route_exists():
    assert app.url_path_for("suggested_rating", experiment_id=uuid.uuid4()).endswith(
        "/suggested-rating"
    )


def test_no_checkins_means_no_suggestion(api):
    client, _, engine = api
    data = suggest(client, add_experiment(engine), "?through=2026-11-28").json()
    assert data["rating"] is None and data["basis"] == "not_enough_during"


def test_improvement_suggests_a_high_rating(api):
    client, _, engine = api
    fill(client, BEFORE, MISSED)
    fill(client, DURING, DONE)
    response = suggest(client, add_experiment(engine), "?through=2026-11-28")
    assert response.status_code == 200
    data = response.json()
    assert data["rating"] == 5 and data["basis"] == "enough_data"
    assert data["during_adherence"] == 100 and data["before_adherence"] == 0
    assert data["during_from"] == "2026-11-23" and data["during_to"] == "2026-11-28"
    assert data["before_from"] == "2026-11-09" and data["before_to"] == "2026-11-22"


def test_a_worse_period_suggests_a_low_rating(api):
    client, _, engine = api
    fill(client, BEFORE, DONE)
    fill(client, DURING, MISSED)
    data = suggest(client, add_experiment(engine), "?through=2026-11-28").json()
    assert data["rating"] == 1 and data["delta"] == -100


def test_no_change_suggests_the_middle(api):
    client, _, engine = api
    fill(client, BEFORE, DONE)
    fill(client, DURING, DONE)
    data = suggest(client, add_experiment(engine), "?through=2026-11-28").json()
    assert data["rating"] == 3 and data["delta"] == 0


def test_no_baseline_means_no_suggestion(api):
    client, _, engine = api
    fill(client, DURING, DONE)
    data = suggest(client, add_experiment(engine), "?through=2026-11-28").json()
    assert data["rating"] is None and data["basis"] == "not_enough_before"


def test_an_ended_experiment_uses_its_own_end_date(api):
    client, _, engine = api
    fill(client, BEFORE, MISSED)
    fill(client, DURING, DONE)
    fill(client, ["2026-11-27", "2026-11-28"], MISSED)  # after the end, must be ignored
    ended = datetime(2026, 11, 25, 20, 0, tzinfo=UTC)
    data = suggest(client, add_experiment(engine, ended_at=ended)).json()
    assert data["during_to"] == "2026-11-25" and data["during_adherence"] == 100


def test_a_running_experiment_needs_through(api):
    client, _, engine = api
    experiment_id = add_experiment(engine)
    assert suggest(client, experiment_id).status_code == 422
    assert suggest(client, experiment_id, "?through=2026-11-01").status_code == 422
    assert suggest(client, experiment_id, "?through=nope").status_code == 422


def test_another_users_or_unknown_experiment_is_404(api):
    client, current, engine = api
    experiment_id = add_experiment(engine, user=USER_B)
    assert suggest(client, experiment_id, "?through=2026-11-28").status_code == 404
    assert suggest(client, uuid.uuid4(), "?through=2026-11-28").status_code == 404
    current["user"] = USER_B
    assert suggest(client, experiment_id, "?through=2026-11-28").status_code == 200


def test_only_the_users_own_checkins_count(api):
    client, current, engine = api
    fill(client, BEFORE, MISSED)
    fill(client, DURING, DONE)
    current["user"] = USER_B
    experiment_id = add_experiment(engine, user=USER_B)
    data = suggest(client, experiment_id, "?through=2026-11-28").json()
    assert data["rating"] is None and data["during_days"] == 0
