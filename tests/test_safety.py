import json

import pytest
from sqlalchemy import select, text

from app.core.config import get_settings
from app.db.models import SafetyEvent
from app.llm.factory import get_llm_provider
from app.llm.fake import FakeProvider
from app.main import app
from app.safety.crisis import check_text, normalize
from app.safety.resources import resources_for

CRISIS_LONG = "I have been thinking about it a lot and I want to kill myself"
CRISIS_SHORT = "I want to die"
NORMAL = (
    "I am a final-year ECE student and I want to become a software developer. "
    "I keep building projects but I procrastinate on hard tasks."
)
OK_JSON = json.dumps({"current_situation": "Final-year ECE student"})


def _count(engine, table):
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()


def _propose(client, auth, body):
    return client.post("/onboarding/propose", json={"text": body}, headers=auth)


@pytest.fixture()
def use_llm():
    def _use(provider):
        app.dependency_overrides[get_llm_provider] = lambda: provider

    return _use


# ---- detector --------------------------------------------------------------

def test_detector_returns_rule_ids_not_text():
    result = check_text(CRISIS_LONG)
    assert result.triggered is True
    assert "en_kill_myself" in result.rule_ids
    assert result.category == "self_harm_risk"
    assert CRISIS_LONG not in repr(result)


def test_empty_and_blank_text_not_triggered():
    assert check_text("").triggered is False
    assert check_text("   \n ").triggered is False


def test_normalization_handles_case_quotes_spacing_and_invisible_characters():
    assert normalize("  I   DON\u2019T\tWant\n") == "i don't want"
    assert check_text("I DON\u2019T WANT TO LIVE ANYMORE").triggered
    assert check_text("i   want   to   d\u200bie").triggered


def test_hindi_and_romanised_statements_are_detected():
    assert check_text("मैं मरना चाहता हूँ").triggered
    assert check_text("main jeena nahi chahta").triggered
    assert check_text("mujhe atmahatya ke khayal aate hain").triggered


def test_everyday_phrases_are_not_flagged():
    for benign in (
        "I am dying to become a software developer",
        "I want to take my life in a new direction",
        "I don't want to live in a hostel",
        "This exam is killing me",
    ):
        assert check_text(benign).triggered is False, benign


# ---- resources -------------------------------------------------------------

def test_every_region_has_resources_and_india_has_tele_manas():
    for region in ("IN", "US", "DEFAULT"):
        assert resources_for(region).resources
    contacts = " ".join(r.contact for r in resources_for("in").resources)
    assert "14416" in contacts
    assert "112" in contacts


def test_unknown_region_falls_back_to_the_default_list():
    assert resources_for("XX") == resources_for("DEFAULT")


# ---- onboarding route ------------------------------------------------------

def test_crisis_requires_auth(client):
    r = client.post("/onboarding/propose", json={"text": CRISIS_LONG})
    assert r.status_code == 401


def test_crisis_text_returns_support_and_no_proposal(client, auth, use_llm):
    use_llm(FakeProvider())
    r = _propose(client, auth, CRISIS_LONG)
    assert r.status_code == 200
    body = r.json()
    assert body["proposal"] is None
    assert body["notes"] == []
    assert body["safety"]["category"] == "self_harm_risk"
    assert body["safety"]["message"]
    contacts = " ".join(item["contact"] for item in body["safety"]["resources"])
    assert "14416" in contacts
    assert "112" in contacts


def test_short_crisis_text_is_not_rejected_as_too_short(client, auth, use_llm):
    use_llm(FakeProvider())
    assert len(CRISIS_SHORT) < 20
    r = _propose(client, auth, CRISIS_SHORT)
    assert r.status_code == 200
    assert r.json()["safety"] is not None


def test_crisis_never_reaches_the_model_or_the_call_log(client, engine, auth, use_llm):
    provider = FakeProvider()
    use_llm(provider)
    _propose(client, auth, CRISIS_LONG)
    assert provider.calls == []
    assert _count(engine, "llm_calls") == 0


def test_crisis_saves_nothing(client, engine, auth, use_llm):
    use_llm(FakeProvider())
    _propose(client, auth, CRISIS_LONG)
    assert _count(engine, "life_model_versions") == 0


def test_safety_event_has_no_user_or_text(client, db, auth, use_llm):
    use_llm(FakeProvider())
    _propose(client, auth, CRISIS_LONG)
    row = db.scalars(select(SafetyEvent)).one()
    assert row.surface == "onboarding"
    assert "en_kill_myself" in row.rule_ids
    columns = {c.name for c in SafetyEvent.__table__.columns}
    assert columns == {"id", "surface", "category", "rule_ids", "created_at"}


def test_response_never_echoes_the_users_text(client, auth, use_llm):
    use_llm(FakeProvider())
    r = _propose(client, auth, CRISIS_LONG)
    assert CRISIS_LONG not in r.text
    assert "kill myself" not in r.text.lower()


def test_crisis_does_not_use_up_the_daily_limit(client, auth, use_llm, monkeypatch):
    monkeypatch.setattr(get_settings(), "onboarding_daily_limit", 1)
    use_llm(FakeProvider(default=OK_JSON))
    assert _propose(client, auth, CRISIS_LONG).json()["safety"] is not None
    assert _propose(client, auth, CRISIS_LONG).json()["safety"] is not None
    r = _propose(client, auth, NORMAL)
    assert r.status_code == 200
    assert r.json()["proposal"] is not None


def test_region_setting_changes_resources(client, auth, use_llm, monkeypatch):
    monkeypatch.setattr(get_settings(), "crisis_region", "US")
    use_llm(FakeProvider())
    body = _propose(client, auth, CRISIS_LONG).json()
    contacts = " ".join(item["contact"] for item in body["safety"]["resources"])
    assert "988" in contacts


def test_normal_text_still_gets_a_proposal(client, auth, use_llm):
    use_llm(FakeProvider(default=OK_JSON))
    body = _propose(client, auth, NORMAL).json()
    assert body["safety"] is None
    assert body["proposal"]["current_situation"] == "Final-year ECE student"


def test_short_normal_text_is_still_rejected(client, auth, use_llm):
    use_llm(FakeProvider(default=OK_JSON))
    assert _propose(client, auth, "too short").status_code == 422
