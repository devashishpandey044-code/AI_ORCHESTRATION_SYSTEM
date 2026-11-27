import pytest
from sqlalchemy import select

from app.db.models import SafetyEvent
from app.methods.loader import get_library

PHONE_TEXT = "my phone keeps buzzing while I study"
# phone_friction is the only seed method that targets both of these, so it ranks first.
PHONE_ROADBLOCKS = ["distraction", "poor_environment"]


def _suggest(client, auth, roadblocks, situation=None):
    body = {"roadblocks": roadblocks}
    if situation is not None:
        body["situation"] = situation
    return client.post("/methods/suggest", json=body, headers=auth)


def _start(client, auth, slug, roadblock):
    body = {"method_slug": slug, "roadblock": roadblock}
    return client.post("/methods/experiments", json=body, headers=auth)


def _end(client, auth, experiment_id, outcome="completed", rating=None):
    body = {"outcome": outcome}
    if rating is not None:
        body["rating"] = rating
    return client.post(f"/methods/experiments/{experiment_id}/end", json=body, headers=auth)


def _slugs(response):
    return [s["slug"] for s in response.json()["suggestions"]]


def test_suggest_requires_auth(client):
    r = client.post("/methods/suggest", json={"roadblocks": ["distraction"]})
    assert r.status_code == 401


def test_suggest_rejects_bad_input(client, auth):
    assert _suggest(client, auth, []).status_code == 422
    assert _suggest(client, auth, ["boredom"]).status_code == 422
    five = ["distraction", "avoidance", "overload", "low_energy", "burnout_risk"]
    assert _suggest(client, auth, five).status_code == 422
    assert client.post("/methods/suggest", json={}, headers=auth).status_code == 422
    assert _suggest(client, auth, ["distraction"], "x" * 1001).status_code == 422


def test_suggest_returns_at_most_two_explained_methods(client, auth):
    r = _suggest(client, auth, PHONE_ROADBLOCKS, PHONE_TEXT)
    assert r.status_code == 200
    suggestions = r.json()["suggestions"]
    assert 1 <= len(suggestions) <= 2
    assert suggestions[0]["slug"] == "phone_friction"
    for suggestion in suggestions:
        assert suggestion["reasons"]
        assert len(suggestion["steps"]) >= 3
        assert suggestion["contraindications"]
        assert suggestion["evidence_level"]
        assert isinstance(suggestion["sources_reviewed"], bool)
        assert suggestion["matched_roadblocks"]


def test_suggestions_come_only_from_the_library(client, auth):
    known = {m.slug for m in get_library()}
    for roadblock in ("distraction", "avoidance", "overload", "ineffective_learning"):
        assert set(_slugs(_suggest(client, auth, [roadblock], PHONE_TEXT))) <= known


def test_suggest_works_without_situation_text(client, auth):
    r = _suggest(client, auth, ["avoidance"])
    assert r.status_code == 200
    assert r.json()["suggestions"]


def test_energy_roadblocks_carry_care_note_and_escalation(client, auth):
    body = _suggest(client, auth, ["low_energy"]).json()
    assert body["suggestions"]
    assert all(s["escalation_note"] for s in body["suggestions"])
    assert "doctor" in body["care_note"]
    assert _suggest(client, auth, ["distraction"]).json()["care_note"] is None


def test_crisis_text_returns_support_and_no_suggestions(client, db, auth):
    r = _suggest(client, auth, ["distraction"], "I want to die")
    body = r.json()
    assert r.status_code == 200
    assert body["suggestions"] == []
    assert body["safety"]["category"] == "self_harm_risk"
    assert db.scalars(select(SafetyEvent)).one().surface == "methods"


def test_active_methods_are_not_suggested_again(client, auth):
    assert _start(client, auth, "phone_friction", "distraction").status_code == 201
    body = _suggest(client, auth, PHONE_ROADBLOCKS, PHONE_TEXT).json()
    assert "phone_friction" in body["already_trying"]
    assert "phone_friction" not in [s["slug"] for s in body["suggestions"]]


def test_abandoned_methods_are_demoted(client, auth):
    exp = _start(client, auth, "phone_friction", "distraction").json()
    assert _end(client, auth, exp["id"], "abandoned").status_code == 200
    assert "phone_friction" not in _slugs(_suggest(client, auth, ["distraction"], PHONE_TEXT))


def test_previously_helpful_methods_are_marked(client, auth):
    exp = _start(client, auth, "phone_friction", "distraction").json()
    _end(client, auth, exp["id"], "completed", rating=5)
    suggestions = _suggest(client, auth, PHONE_ROADBLOCKS, PHONE_TEXT).json()["suggestions"]
    phone = next(s for s in suggestions if s["slug"] == "phone_friction")
    assert "You rated this helpful before." in phone["reasons"]


# ---- the library itself ----------------------------------------------------

def test_library_endpoints_require_auth(client):
    assert client.get("/methods").status_code == 401
    assert client.get("/methods/phone_friction").status_code == 401


def test_list_and_get_library_methods(client, auth):
    listed = client.get("/methods", headers=auth).json()
    assert len(listed) == len(get_library())
    assert all({"slug", "title", "summary", "targets", "evidence_level"} <= set(m) for m in listed)
    one = client.get("/methods/phone_friction", headers=auth)
    assert one.status_code == 200
    assert len(one.json()["steps"]) >= 3
    assert one.json()["contraindications"]


def test_unknown_library_method_returns_404(client, auth):
    assert client.get("/methods/does_not_exist", headers=auth).status_code == 404


def test_experiments_path_is_not_shadowed_by_the_slug_route(client, auth):
    r = client.get("/methods/experiments", headers=auth)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.parametrize("roadblock", ["distraction"])
def test_suggestions_are_deterministic(client, auth, roadblock):
    first = _slugs(_suggest(client, auth, [roadblock], PHONE_TEXT))
    second = _slugs(_suggest(client, auth, [roadblock], PHONE_TEXT))
    assert first == second
