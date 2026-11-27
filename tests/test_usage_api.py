import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.db.models import Base, LLMCall
from app.db.session import get_db
from app.main import app

USER_A = uuid.uuid4()
USER_B = uuid.uuid4()
HAIKU = "claude-haiku-5-5"


@pytest.fixture
def api():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine, tables=[LLMCall.__table__])
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


def add_call(engine, user=USER_A, days_ago=1, **kw):
    fields = dict(
        purpose="roadblocks",
        provider="anthropic",
        model=HAIKU,
        prompt_version="v1",
        attempts=1,
        input_tokens=1000,
        output_tokens=500,
        latency_ms=100.0,
        success=True,
    )
    with Session(engine) as db:
        db.add(
            LLMCall(
                user_id=user,
                created_at=datetime.now(UTC) - timedelta(days=days_ago),
                **(fields | kw),
            )
        )
        db.commit()


def test_a_user_with_no_calls_gets_an_empty_summary(api):
    client, _, _ = api
    body = client.get("/usage").json()
    assert body["days"] == 7
    assert body["overall"]["calls"] == 0
    assert body["overall"]["success_percent"] is None
    assert body["by_purpose"] == [] and body["by_model"] == []


def test_the_summary_adds_up_calls_tokens_and_cost(api):
    client, _, engine = api
    add_call(engine)
    add_call(engine, purpose="onboarding", output_tokens=100)
    add_call(engine, success=False, attempts=3, latency_ms=900.0)
    body = client.get("/usage").json()
    overall = body["overall"]
    assert overall["calls"] == 3
    assert overall["failures"] == 1
    assert overall["success_percent"] == 67
    assert overall["retries"] == 2
    assert overall["input_tokens"] == 3000
    assert overall["output_tokens"] == 1100
    assert overall["estimated_cost_micro_usd"] == 850  # 350 + 150 + 350
    assert [g["key"] for g in body["by_purpose"]] == ["onboarding", "roadblocks"]
    assert [g["key"] for g in body["by_model"]] == [HAIKU]


def test_the_cost_is_the_hand_calculated_figure(api):
    client, _, engine = api
    add_call(engine)  # 1000 in, 500 out = 350 micro-dollars
    assert client.get("/usage").json()["overall"]["estimated_cost_micro_usd"] == 350


def test_calls_older_than_the_window_are_left_out(api):
    client, _, engine = api
    add_call(engine, days_ago=1)
    add_call(engine, days_ago=10)
    assert client.get("/usage?days=7").json()["overall"]["calls"] == 1
    assert client.get("/usage?days=30").json()["overall"]["calls"] == 2


def test_other_users_and_unowned_calls_are_never_counted(api):
    client, current, engine = api
    add_call(engine, user=USER_A)
    add_call(engine, user=USER_B)
    add_call(engine, user=None)
    assert client.get("/usage").json()["overall"]["calls"] == 1
    current["user"] = USER_B
    assert client.get("/usage").json()["overall"]["calls"] == 1


def test_an_unknown_model_is_listed_but_not_costed(api):
    client, _, engine = api
    add_call(engine, model="fake-1")
    body = client.get("/usage").json()
    assert body["overall"]["unpriced_calls"] == 1
    assert body["overall"]["estimated_cost_micro_usd"] == 0
    assert "estimate" in body["note"]


@pytest.mark.parametrize("days", ["0", "-1", "91", "x", "1.5", ""])
def test_a_bad_window_is_a_422(api, days):
    client, _, _ = api
    assert client.get(f"/usage?days={days}").status_code == 422


def test_a_damaged_stored_row_is_a_500_not_a_wrong_number(api):
    client, _, engine = api
    add_call(engine, attempts=0)
    response = client.get("/usage")
    assert response.status_code == 500
    assert "damaged" in response.json()["detail"]


def test_the_response_never_contains_error_text(api):
    client, _, engine = api
    add_call(engine, success=False, error="secret detail from the provider")
    assert "secret detail" not in client.get("/usage").text
