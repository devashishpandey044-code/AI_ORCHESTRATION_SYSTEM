import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.db.models import ExperimentStatus, MethodExperiment


def _start(client, auth, slug="phone_friction", roadblock="distraction"):
    body = {"method_slug": slug, "roadblock": roadblock}
    return client.post("/methods/experiments", json=body, headers=auth)


def _end(client, auth, experiment_id, outcome="completed", rating=None):
    body = {"outcome": outcome}
    if rating is not None:
        body["rating"] = rating
    return client.post(f"/methods/experiments/{experiment_id}/end", json=body, headers=auth)


def _user_id(client, headers):
    return uuid.UUID(client.get("/auth/me", headers=headers).json()["id"])


def _count(engine, table):
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()


def test_start_experiment(client, auth):
    r = _start(client, auth)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "active"
    assert body["method_slug"] == "phone_friction"
    assert body["method_title"]
    assert body["roadblock"] == "distraction"
    assert body["rating"] is None
    assert body["ended_at"] is None


def test_start_requires_auth(client):
    r = client.post("/methods/experiments", json={"method_slug": "x", "roadblock": "overload"})
    assert r.status_code == 401


def test_unknown_method_returns_404(client, auth):
    assert _start(client, auth, "does_not_exist", "distraction").status_code == 404


def test_roadblock_the_method_does_not_target_is_rejected(client, auth):
    assert _start(client, auth, "phone_friction", "ineffective_learning").status_code == 422
    assert _start(client, auth, "phone_friction", "boredom").status_code == 422


def test_same_method_cannot_be_active_twice(client, auth):
    assert _start(client, auth).status_code == 201
    assert _start(client, auth).status_code == 409


def test_active_experiment_limit(client, auth, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_active_experiments", 1)
    assert _start(client, auth, "phone_friction", "distraction").status_code == 201
    assert _start(client, auth, "protected_focus_block", "distraction").status_code == 409


def test_a_method_can_be_tried_again_after_it_ends(client, auth):
    first = _start(client, auth).json()
    assert _end(client, auth, first["id"], "abandoned").status_code == 200
    assert _start(client, auth).status_code == 201


def test_end_completed_with_rating(client, auth):
    exp = _start(client, auth).json()
    r = _end(client, auth, exp["id"], "completed", rating=4)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert body["rating"] == 4
    assert body["ended_at"] is not None


def test_end_abandoned_without_rating(client, auth):
    exp = _start(client, auth).json()
    body = _end(client, auth, exp["id"], "abandoned").json()
    assert body["status"] == "abandoned"
    assert body["rating"] is None


def test_cannot_end_twice(client, auth):
    exp = _start(client, auth).json()
    assert _end(client, auth, exp["id"]).status_code == 200
    assert _end(client, auth, exp["id"]).status_code == 409


def test_end_body_is_validated(client, auth):
    exp = _start(client, auth).json()
    for rating in (0, 6):
        assert _end(client, auth, exp["id"], "completed", rating).status_code == 422
    assert _end(client, auth, exp["id"], "active").status_code == 422
    assert _end(client, auth, exp["id"], "nonsense").status_code == 422
    # still active after all the failed attempts
    active = client.get("/methods/experiments?status=active", headers=auth).json()
    assert active[0]["id"] == exp["id"]


def test_experiments_are_private_to_their_owner(client, auth, other_auth):
    exp = _start(client, auth).json()
    assert _end(client, other_auth, exp["id"]).status_code == 404
    assert client.get("/methods/experiments", headers=other_auth).json() == []
    # Bob can try the same method independently
    assert _start(client, other_auth).status_code == 201


def test_list_can_filter_by_status(client, auth):
    first = _start(client, auth, "phone_friction", "distraction").json()
    _start(client, auth, "protected_focus_block", "distraction")
    _end(client, auth, first["id"])
    active = client.get("/methods/experiments?status=active", headers=auth).json()
    done = client.get("/methods/experiments?status=completed", headers=auth).json()
    assert [e["method_slug"] for e in active] == ["protected_focus_block"]
    assert [e["method_slug"] for e in done] == ["phone_friction"]
    assert len(client.get("/methods/experiments", headers=auth).json()) == 2


def test_database_blocks_two_active_experiments_for_one_method(client, db, auth):
    uid = _user_id(client, auth)

    def row():
        return MethodExperiment(
            user_id=uid,
            method_slug="phone_friction",
            roadblock="distraction",
            status=ExperimentStatus.ACTIVE,
        )

    db.add(row())
    db.commit()
    db.add(row())
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_experiment_for_a_removed_method_still_lists(client, db, auth):
    uid = _user_id(client, auth)
    db.add(
        MethodExperiment(
            user_id=uid,
            method_slug="removed_method",
            roadblock="distraction",
            status=ExperimentStatus.COMPLETED,
            rating=3,
        )
    )
    db.commit()
    listed = client.get("/methods/experiments", headers=auth).json()
    assert [e["method_slug"] for e in listed] == ["removed_method"]
    assert listed[0]["method_title"] is None


def test_experiments_are_exported_and_deleted_with_the_account(client, engine, auth, other_auth):
    _start(client, auth)
    _start(client, other_auth)
    exported = client.get("/auth/me/export", headers=auth).json()
    assert [e["method_slug"] for e in exported["method_experiments"]] == ["phone_friction"]
    assert client.delete("/auth/me", headers=auth).status_code == 204
    assert _count(engine, "method_experiments") == 1  # only Bob's remains
