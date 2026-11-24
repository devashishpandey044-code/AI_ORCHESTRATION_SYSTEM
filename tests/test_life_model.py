import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db.models import LifeModelSource, LifeModelVersion, LLMCall
from app.llm.fake import FakeProvider
from app.llm.structured import complete_structured
from app.schemas.life_model import LifeModelData, ModelItem, Provenance
from app.services import life_model as lm
from app.services.llm_calls import record_llm_call, record_structured_result


def _user_id(client, headers) -> uuid.UUID:
    return uuid.UUID(client.get("/auth/me", headers=headers).json()["id"])


def _count(engine, table):
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()


def _log(db, uid, **overrides):
    values = dict(
        user_id=uid, purpose="p", provider="fake", model="m", prompt_version="v",
        attempts=1, input_tokens=1, output_tokens=1, latency_ms=1.0, success=True,
    )
    return record_llm_call(db, **(values | overrides))


# ---- schema ----------------------------------------------------------------

def test_schema_defaults():
    data = LifeModelData()
    assert data.current_situation is None
    assert data.vision == []
    assert ModelItem(text="x").provenance == Provenance.STATED


def test_item_text_is_stripped():
    assert ModelItem(text="  hello  ").text == "hello"


def test_item_rejects_blank_text():
    with pytest.raises(ValidationError):
        ModelItem(text="   ")


def test_schema_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        LifeModelData.model_validate({"hobbies": []})


def test_schema_limits_list_size():
    with pytest.raises(ValidationError):
        LifeModelData(vision=[ModelItem(text=str(i)) for i in range(11)])


def test_item_rejects_unknown_provenance():
    with pytest.raises(ValidationError):
        ModelItem(text="x", provenance="guess")


# ---- versioned storage -----------------------------------------------------

def test_versions_increment_and_current_is_latest(client, db, auth):
    uid = _user_id(client, auth)
    assert lm.get_current(db, uid) is None
    v1 = lm.save_new_version(
        db, uid, LifeModelData(current_situation="Student"), LifeModelSource.ONBOARDING
    )
    v2 = lm.save_new_version(
        db, uid, LifeModelData(current_situation="Graduate"), LifeModelSource.USER_EDIT
    )
    assert (v1.version, v2.version) == (1, 2)
    current = lm.get_current(db, uid)
    assert current.version == 2
    assert current.source == LifeModelSource.USER_EDIT
    assert lm.parse_data(current).current_situation == "Graduate"


def test_data_round_trips_with_provenance(client, db, auth):
    uid = _user_id(client, auth)
    data = LifeModelData(
        vision=[
            ModelItem(
                text="Become a backend engineer",
                provenance=Provenance.STATED,
                evidence="I want to be a backend engineer",
            )
        ],
        concerns=[ModelItem(text="Procrastination", provenance=Provenance.INFERRED)],
    )
    lm.save_new_version(db, uid, data, LifeModelSource.ONBOARDING)
    assert lm.parse_data(lm.get_current(db, uid)) == data


def test_versions_are_per_user(client, db, auth, other_auth):
    a, b = _user_id(client, auth), _user_id(client, other_auth)
    lm.save_new_version(db, a, LifeModelData(), LifeModelSource.ONBOARDING)
    lm.save_new_version(db, a, LifeModelData(), LifeModelSource.USER_EDIT)
    first_for_b = lm.save_new_version(db, b, LifeModelData(), LifeModelSource.ONBOARDING)
    assert first_for_b.version == 1
    assert lm.get_current(db, b).version == 1


def test_list_versions_newest_first(client, db, auth):
    uid = _user_id(client, auth)
    for _ in range(3):
        lm.save_new_version(db, uid, LifeModelData(), LifeModelSource.USER_EDIT)
    assert [v.version for v in lm.list_versions(db, uid)] == [3, 2, 1]


def test_get_version_is_scoped_to_user(client, db, auth, other_auth):
    a, b = _user_id(client, auth), _user_id(client, other_auth)
    lm.save_new_version(db, a, LifeModelData(), LifeModelSource.ONBOARDING)
    assert lm.get_version(db, a, 1).version == 1
    assert lm.get_version(db, a, 99) is None
    assert lm.get_version(db, b, 1) is None


def test_duplicate_version_rejected_by_database(client, db, auth):
    uid = _user_id(client, auth)
    lm.save_new_version(db, uid, LifeModelData(), LifeModelSource.ONBOARDING)
    db.add(LifeModelVersion(user_id=uid, version=1, source=LifeModelSource.SYSTEM, data={}))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ---- LLM call log ----------------------------------------------------------

def test_record_llm_call_truncates_long_errors(client, db, auth):
    uid = _user_id(client, auth)
    row = _log(db, uid, success=False, error="x" * 900, attempts=2)
    assert row.success is False
    assert len(row.error) == 500
    assert row.created_at is not None


def test_record_structured_result(client, db, auth):
    uid = _user_id(client, auth)
    result = complete_structured(
        FakeProvider(["{}"]), LifeModelData, system="s", user="u", prompt_version="p1"
    )
    row = record_structured_result(db, user_id=uid, purpose="onboarding_extract", result=result)
    assert row.success is True
    assert row.attempts == 1
    assert row.provider == "fake"
    assert row.model == "fake-1"
    assert row.prompt_version == "p1"
    assert row.input_tokens == result.input_tokens


def test_llm_call_table_stores_no_prompt_or_response_text():
    columns = {c.name for c in LLMCall.__table__.columns}
    assert not columns & {"prompt", "response", "content", "text", "system", "user_message"}


# ---- account export and deletion cover the new tables ----------------------

def test_export_includes_life_model_versions(client, db, auth):
    uid = _user_id(client, auth)
    lm.save_new_version(
        db, uid, LifeModelData(current_situation="Final-year student"), LifeModelSource.ONBOARDING
    )
    body = client.get("/auth/me/export", headers=auth).json()
    assert [v["version"] for v in body["life_model_versions"]] == [1]
    assert body["life_model_versions"][0]["source"] == "onboarding"
    assert body["life_model_versions"][0]["data"]["current_situation"] == "Final-year student"


def test_delete_account_removes_life_model_and_llm_calls(client, db, engine, auth, other_auth):
    a, b = _user_id(client, auth), _user_id(client, other_auth)
    for uid in (a, b):
        lm.save_new_version(db, uid, LifeModelData(), LifeModelSource.ONBOARDING)
        _log(db, uid)

    assert client.delete("/auth/me", headers=auth).status_code == 204

    assert _count(engine, "life_model_versions") == 1
    assert _count(engine, "llm_calls") == 1
    remaining = db.scalars(select(LifeModelVersion)).all()
    assert [r.user_id for r in remaining] == [b]
