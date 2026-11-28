import uuid

import pytest

from app.db.intake_models import Obstacle
from app.intake import questions
from app.intake.questions import QuestionKind
from app.intake.types import ObstacleStatus
from app.methods.taxonomy import RoadblockType
from app.services import intake as service

# Matches a crisis rule, so the safety check fires before anything is stored.
CRISIS = "I keep thinking about ending my life and I cannot focus on anything"
PHONE = "I lose the whole evening to my phone"


def _put(client, auth, key, value):
    return client.put(f"/intake/answers/{key}", json={"value": value}, headers=auth)


def _add(client, auth, text, severity=None):
    body = {"text": text}
    if severity is not None:
        body["severity"] = severity
    return client.post("/obstacles", json=body, headers=auth)


def _new_id(client, auth, text=PHONE):
    response = _add(client, auth, text)
    assert response.status_code == 201, response.text
    return response.json()["obstacle"]["id"]


def _row(db, obstacle_id):
    return db.get(Obstacle, uuid.UUID(obstacle_id))


def _sample(question) -> str:
    """A valid answer for any question kind, so a test can complete the intake."""
    if question.kind is QuestionKind.TIME:
        return "07:30"
    if question.kind is QuestionKind.INT:
        return str(question.min_value)
    if question.kind is QuestionKind.CHOICE:
        return question.choices[0]
    return "something I typed"


# --- the catalogue ---


def test_the_catalogue_is_public_and_in_asking_order(client):
    response = client.get("/intake/questions")
    assert response.status_code == 200
    assert [q["key"] for q in response.json()] == list(questions.keys())


# --- answers ---


def test_saving_an_answer_then_reading_it_back(client, auth):
    response = _put(client, auth, "weekly_fixed", "Classes 9 to 1, lab Tue and Thu")
    assert response.status_code == 200
    assert response.json()["safety"] is None
    assert response.json()["answer"]["question_key"] == "weekly_fixed"
    stored = client.get("/intake/answers", headers=auth).json()
    assert [a["question_key"] for a in stored] == ["weekly_fixed"]


def test_answering_the_same_question_again_replaces_it(client, auth):
    _put(client, auth, "sleep_time", "23:30")
    _put(client, auth, "sleep_time", "00:45")
    stored = client.get("/intake/answers", headers=auth).json()
    assert len(stored) == 1
    assert stored[0]["value"] == "00:45"


def test_an_unknown_question_is_rejected(client, auth):
    response = _put(client, auth, "not_a_question", "whatever")
    assert response.status_code == 422
    assert "no such question" in response.json()["detail"]


def test_a_bad_time_is_rejected_with_a_plain_message(client, auth):
    response = _put(client, auth, "sleep_time", "half eleven")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "HH:MM" in detail
    # The pydantic prefix is stripped before the person sees it.
    assert "Value error" not in detail


def test_answers_come_back_in_asking_order(client, auth):
    _put(client, auth, "biggest_obstacle", PHONE)
    _put(client, auth, "weekly_fixed", "Classes 9 to 1")
    stored = client.get("/intake/answers", headers=auth).json()
    assert [a["question_key"] for a in stored] == ["weekly_fixed", "biggest_obstacle"]


def test_progress_counts_the_required_questions(client, auth):
    before = client.get("/intake/progress", headers=auth).json()
    assert before["answered"] == 0
    assert before["complete"] is False
    assert before["required_total"] == len(questions.required_keys())
    assert "sleep_time" in before["missing_required"]

    _put(client, auth, "sleep_time", "23:30")
    after = client.get("/intake/progress", headers=auth).json()
    assert after["answered"] == 1
    assert "sleep_time" not in after["missing_required"]


def test_the_intake_is_complete_once_every_required_question_is_answered(client, auth):
    for key in questions.required_keys():
        response = _put(client, auth, key, _sample(questions.get(key)))
        assert response.status_code == 200, response.text
    progress = client.get("/intake/progress", headers=auth).json()
    assert progress["missing_required"] == []
    assert progress["complete"] is True


def test_answers_are_private_to_their_user(client, auth, other_auth):
    _put(client, auth, "sleep_time", "23:30")
    assert client.get("/intake/answers", headers=other_auth).json() == []


def test_saving_an_answer_needs_a_token(client):
    response = client.put("/intake/answers/sleep_time", json={"value": "23:30"})
    assert response.status_code == 401


def test_a_crisis_disclosure_in_an_answer_stores_nothing(client, auth):
    response = _put(client, auth, "biggest_obstacle", CRISIS)
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] is None
    assert body["safety"]["category"]
    assert body["safety"]["resources"]
    # The point of the check: the text was never written down.
    assert client.get("/intake/answers", headers=auth).json() == []


# --- obstacles ---


def test_a_new_problem_is_recorded_as_stated_and_unclassified(client, auth):
    response = _add(client, auth, PHONE, 4)
    assert response.status_code == 201
    obstacle = response.json()["obstacle"]
    assert obstacle["status"] == ObstacleStatus.STATED
    assert obstacle["roadblock_type"] is None
    assert obstacle["severity"] == 4


def test_a_crisis_disclosure_is_not_recorded_as_a_problem(client, auth):
    response = _add(client, auth, CRISIS)
    assert response.status_code == 200
    assert response.json()["obstacle"] is None
    assert response.json()["safety"]["resources"]
    assert client.get("/obstacles", headers=auth).json() == []


def test_listing_can_filter_by_status(client, auth):
    _new_id(client, auth)
    assert len(client.get("/obstacles", headers=auth).json()) == 1
    assert client.get("/obstacles?status=resolved", headers=auth).json() == []


def test_severity_can_be_changed_on_its_own(client, auth):
    obstacle_id = _new_id(client, auth)
    response = client.patch(f"/obstacles/{obstacle_id}", json={"severity": 2}, headers=auth)
    assert response.status_code == 200
    assert response.json()["severity"] == 2


def test_an_empty_change_is_rejected(client, auth):
    obstacle_id = _new_id(client, auth)
    response = client.patch(f"/obstacles/{obstacle_id}", json={}, headers=auth)
    assert response.status_code == 422


@pytest.mark.parametrize("status", ["stated", "out_of_scope"])
def test_a_user_cannot_set_the_system_statuses(client, auth, status):
    obstacle_id = _new_id(client, auth)
    response = client.patch(f"/obstacles/{obstacle_id}", json={"status": status}, headers=auth)
    assert response.status_code == 422


def test_an_unclassified_problem_cannot_be_made_active(client, auth):
    obstacle_id = _new_id(client, auth)
    response = client.patch(f"/obstacles/{obstacle_id}", json={"status": "active"}, headers=auth)
    assert response.status_code == 409
    assert "classified" in response.json()["detail"]


def test_resolving_sets_a_resolved_time_and_reopening_clears_it(client, auth, db):
    obstacle_id = _new_id(client, auth)
    row = _row(db, obstacle_id)
    row.roadblock_type = RoadblockType.DISTRACTION
    db.commit()

    resolved = client.patch(f"/obstacles/{obstacle_id}", json={"status": "resolved"}, headers=auth)
    assert resolved.status_code == 200
    assert resolved.json()["resolved_at"] is not None

    reopened = client.patch(f"/obstacles/{obstacle_id}", json={"status": "active"}, headers=auth)
    assert reopened.status_code == 200
    assert reopened.json()["resolved_at"] is None


def test_an_out_of_scope_problem_is_frozen_but_can_still_be_deleted(client, auth, db):
    obstacle_id = _new_id(client, auth, "Something the app should not advise on")
    row = _row(db, obstacle_id)
    row.status = ObstacleStatus.OUT_OF_SCOPE
    db.commit()

    frozen = client.patch(f"/obstacles/{obstacle_id}", json={"severity": 2}, headers=auth)
    assert frozen.status_code == 409
    # Removing their own data stays theirs to do.
    assert client.delete(f"/obstacles/{obstacle_id}", headers=auth).status_code == 204


def test_one_user_cannot_see_or_change_anothers_problem(client, auth, other_auth):
    obstacle_id = _new_id(client, auth)
    assert client.get("/obstacles", headers=other_auth).json() == []
    patched = client.patch(f"/obstacles/{obstacle_id}", json={"severity": 2}, headers=other_auth)
    assert patched.status_code == 404
    assert client.delete(f"/obstacles/{obstacle_id}", headers=other_auth).status_code == 404


def test_deleting_a_problem_removes_it(client, auth):
    obstacle_id = _new_id(client, auth)
    assert client.delete(f"/obstacles/{obstacle_id}", headers=auth).status_code == 204
    assert client.get("/obstacles", headers=auth).json() == []


def test_the_recorded_problem_cap_is_enforced(client, auth, monkeypatch):
    monkeypatch.setattr(service, "MAX_OBSTACLES", 2)
    assert _add(client, auth, "The first problem").status_code == 201
    assert _add(client, auth, "The second problem").status_code == 201
    response = _add(client, auth, "The third problem")
    assert response.status_code == 409
    assert "2 problems" in response.json()["detail"]
