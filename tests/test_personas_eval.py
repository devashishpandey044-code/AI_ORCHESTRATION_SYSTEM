from types import SimpleNamespace

from app.evals import personas as eval_module
from app.evals.personas import METRICS, run_personas
from app.evals.personas_cases import KIND_METRIC, PERSONAS
from app.planning.validator import Violation, ViolationCode


def test_there_are_enough_personas_and_ids_are_unique():
    ids = [p.id for p in PERSONAS]
    assert len(ids) >= 30
    assert len(ids) == len(set(ids))
    assert all(p.case.id == p.id for p in PERSONAS)


def test_every_metric_is_covered_by_some_persona():
    assert {KIND_METRIC[p.kind] for p in PERSONAS} == {"detection", "grounding", "safety"}


def test_the_eval_passes_on_the_real_product():
    report = run_personas()
    assert report.failures == []
    assert report.personas == len(PERSONAS)
    for name in METRICS:
        assert report.scores[name].total > 0
        assert report.scores[name].percent == 100


def test_wrong_label_is_caught_by_the_detection_metric():
    persona = next(p for p in PERSONAS if p.id == "phone_buzzing")
    wrong = type(persona.case)(
        id="phone_buzzing",
        text=persona.case.text,
        model_output=persona.case.model_output,
        expect_roadblocks={},
        expect_model_calls=1,
    )
    report = run_personas([type(persona)(persona.id, persona.kind, wrong)])
    assert report.scores["detection"].ok == 0
    assert report.failures


def test_a_broken_plan_is_caught_by_the_plan_metric(monkeypatch):
    broken = [Violation(ViolationCode.OVERLAP, "made up")]
    monkeypatch.setattr(eval_module, "validate_schedule", lambda *args: broken)
    persona = next(p for p in PERSONAS if p.id == "calm_words")
    report = run_personas([persona])
    assert report.scores["plan constraints"].ok == 0
    assert any("plan broke a rule" in f for f in report.failures)


def test_a_wrong_adherence_is_caught_by_the_checkin_metric(monkeypatch):
    monkeypatch.setattr(
        eval_module, "compare_day", lambda planned, checkin: SimpleNamespace(adherence_percent=-1)
    )
    persona = next(p for p in PERSONAS if p.id == "calm_words")
    report = run_personas([persona])
    assert report.scores["check-ins"].ok == 0
    assert report.failures


def test_a_crisis_persona_gets_no_plan():
    persona = next(p for p in PERSONAS if p.id == "crisis_short")
    report = run_personas([persona])
    assert report.scores["safety"].total == 1
    assert report.scores["plan constraints"].total == 0
