import json

import pytest
from sqlalchemy import select, text

from app.core.config import get_settings
from app.db.models import LLMCall, SafetyEvent
from app.llm.base import LLMProviderError
from app.llm.factory import get_llm_provider
from app.llm.fake import FakeProvider
from app.main import app

TEXT = (
    "My phone keeps distracting me and I keep putting off my project "
    "because I do not know where to start."
)
CRISIS = "I have been thinking about it a lot and I want to kill myself"
DISTRACTION_DATA = {"days_covered": 7, "focus_blocks_planned": 7, "unplanned_phone_checks": 28}


class BrokenProvider:
    name = "broken"

    def complete(self, *, system, user, max_tokens=1024):
        raise LLMProviderError("Anthropic returned HTTP 500")


def _model(*items):
    return json.dumps({"roadblocks": list(items)})


def _detect(client, auth, **body):
    return client.post("/roadblocks/detect", json=body, headers=auth)


def _count(engine, table):
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()


@pytest.fixture()
def use_llm():
    def _use(provider):
        app.dependency_overrides[get_llm_provider] = lambda: provider

    return _use


def test_requires_auth(client):
    assert client.post("/roadblocks/detect", json={"text": TEXT}).status_code == 401


def test_needs_text_or_execution(client, auth):
    assert _detect(client, auth).status_code == 422
    assert _detect(client, auth, text="   ").status_code == 422


def test_text_only_detects_and_logs_the_call(client, db, auth, use_llm):
    use_llm(
        FakeProvider([_model({"roadblock": "distraction", "quote": "My phone keeps distracting me"})])
    )
    r = _detect(client, auth, text=TEXT)
    assert r.status_code == 200
    body = r.json()
    assert [x["roadblock"] for x in body["roadblocks"]] == ["distraction"]
    assert body["roadblocks"][0]["strength"] == "strong"
    assert body["roadblocks"][0]["signals"][0]["source"] == "user_words"
    row = db.scalars(select(LLMCall)).one()
    assert row.purpose == "roadblock_detect"
    assert row.success is True


def test_execution_only_makes_no_model_call(client, engine, auth, use_llm):
    provider = FakeProvider()
    use_llm(provider)
    r = _detect(client, auth, execution=DISTRACTION_DATA)
    assert r.status_code == 200
    assert [x["roadblock"] for x in r.json()["roadblocks"]] == ["distraction"]
    assert provider.calls == []
    assert _count(engine, "llm_calls") == 0


def test_text_and_execution_are_merged(client, auth, use_llm):
    use_llm(
        FakeProvider(
            [
                _model(
                    {"roadblock": "distraction", "quote": "My phone keeps distracting me"},
                    {"roadblock": "avoidance", "quote": "keep putting off my project"},
                )
            ]
        )
    )
    r = _detect(client, auth, text=TEXT, execution=DISTRACTION_DATA)
    roadblocks = r.json()["roadblocks"]
    assert [x["roadblock"] for x in roadblocks] == ["distraction", "avoidance"]
    assert {s["source"] for s in roadblocks[0]["signals"]} == {"data", "user_words"}


def test_invented_roadblock_is_dropped_with_a_note(client, auth, use_llm):
    use_llm(FakeProvider([_model({"roadblock": "boredom", "quote": "x"})]))
    body = _detect(client, auth, text=TEXT).json()
    assert body["roadblocks"] == []
    assert any("boredom" in note for note in body["notes"])


def test_sensitive_roadblocks_add_a_care_note(client, auth, use_llm):
    use_llm(FakeProvider())
    execution = {"days_covered": 14, "energy_ratings": [2] * 14, "low_energy_streak_days": 14}
    body = _detect(client, auth, execution=execution).json()
    assert {x["roadblock"] for x in body["roadblocks"]} == {"low_energy", "burnout_risk"}
    assert all(x["sensitive"] for x in body["roadblocks"])
    assert "doctor" in body["care_note"]


def test_crisis_text_returns_support_and_skips_everything(client, db, engine, auth, use_llm):
    provider = FakeProvider()
    use_llm(provider)
    r = _detect(client, auth, text=CRISIS, execution=DISTRACTION_DATA)
    body = r.json()
    assert r.status_code == 200
    assert body["roadblocks"] == []
    assert body["safety"]["category"] == "self_harm_risk"
    assert provider.calls == []
    assert _count(engine, "llm_calls") == 0
    assert db.scalars(select(SafetyEvent)).one().surface == "roadblocks"


def test_short_crisis_text_is_not_rejected_as_too_short(client, auth, use_llm):
    use_llm(FakeProvider())
    r = _detect(client, auth, text="I want to die")
    assert r.status_code == 200
    assert r.json()["safety"] is not None


def test_short_normal_text_is_rejected(client, auth, use_llm):
    use_llm(FakeProvider())
    assert _detect(client, auth, text="too short").status_code == 422


def test_provider_failure_returns_503_without_echoing_text(client, auth, use_llm):
    use_llm(BrokenProvider())
    r = _detect(client, auth, text=TEXT)
    assert r.status_code == 503
    assert TEXT not in r.text


def test_invalid_model_output_returns_502_and_logs_failure(client, db, auth, use_llm):
    use_llm(FakeProvider(default="not json"))
    assert _detect(client, auth, text=TEXT).status_code == 502
    row = db.scalars(select(LLMCall)).one()
    assert row.success is False
    assert row.attempts == 2
    assert row.error == "validation_failed"


def test_provider_failure_with_activity_data_degrades_gracefully(client, auth, use_llm):
    use_llm(BrokenProvider())
    r = _detect(client, auth, text=TEXT, execution=DISTRACTION_DATA)
    body = r.json()
    assert r.status_code == 200
    assert [x["roadblock"] for x in body["roadblocks"]] == ["distraction"]
    assert any("unavailable" in note for note in body["notes"])


def test_daily_limit_is_per_user(client, auth, other_auth, use_llm, monkeypatch):
    monkeypatch.setattr(get_settings(), "roadblock_daily_limit", 2)
    use_llm(FakeProvider(default=_model()))
    assert _detect(client, auth, text=TEXT).status_code == 200
    assert _detect(client, auth, text=TEXT).status_code == 200
    assert _detect(client, auth, text=TEXT).status_code == 429
    assert _detect(client, other_auth, text=TEXT).status_code == 200
