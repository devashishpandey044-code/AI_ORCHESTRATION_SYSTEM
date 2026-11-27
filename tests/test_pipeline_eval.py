from dataclasses import replace

from app.evals.pipeline import check_invariants, main, run_case, run_pipeline_eval
from app.evals.pipeline_cases import CASES
from app.methods.loader import get_method
from app.methods.taxonomy import RoadblockType as R
from app.schemas.methods import SuggestedMethod, SuggestResponse
from app.services.methods import method_to_out
from tests.test_retrieval import make_method


def suggested(method, matched, reasons=("Because it fits.",)):
    return SuggestedMethod(
        **method_to_out(method).model_dump(),
        matched_roadblocks=list(matched),
        reasons=list(reasons),
    )


def test_gate_cases_all_pass():
    report = run_pipeline_eval()
    assert report.failures == []
    assert report.ok == report.total == len(CASES)
    assert (report.combos, report.requests) == (255, 510)


def test_case_ids_are_unique():
    ids = [case.id for case in CASES]
    assert len(ids) == len(set(ids))


def test_cli_exits_zero_when_gate_passes(capsys):
    assert main() == 0
    out = capsys.readouterr().out
    assert "RESULT: PASS" in out
    assert "golden cases correct" in out


def test_check_invariants_accepts_a_clean_response():
    phone = get_method("phone_friction")
    response = SuggestResponse(suggestions=[suggested(phone, [R.DISTRACTION])])
    assert check_invariants([R.DISTRACTION], response) == []


def test_check_invariants_catches_violations():
    phone = get_method("phone_friction")
    focus = get_method("protected_focus_block")
    habit = get_method("implementation_intentions")
    asked = [R.DISTRACTION]

    three = SuggestResponse(suggestions=[suggested(m, asked) for m in (phone, focus, habit)])
    assert any("limit is 2" in p for p in check_invariants(asked, three))

    twice = SuggestResponse(suggestions=[suggested(phone, asked), suggested(phone, asked)])
    assert any("twice" in p for p in check_invariants(asked, twice))

    invented = make_method("made_up_method", [R.DISTRACTION])
    response = SuggestResponse(suggestions=[suggested(invented, asked)])
    assert any("not in the library" in p for p in check_invariants(asked, response))

    wrong_match = SuggestResponse(suggestions=[suggested(phone, [R.AVOIDANCE])])
    assert any("not requested" in p for p in check_invariants(asked, wrong_match))

    no_reasons = SuggestResponse(suggestions=[suggested(phone, asked, reasons=())])
    assert any("no reasons" in p for p in check_invariants(asked, no_reasons))

    energy = make_method("energy_method", [R.LOW_ENERGY]).model_copy(
        update={"escalation_note": None}
    )
    response = SuggestResponse(suggestions=[suggested(energy, [R.LOW_ENERGY])])
    problems = check_invariants([R.LOW_ENERGY], response)
    assert any("no escalation note" in p for p in problems)
    assert any("care note" in p for p in problems)

    calm = SuggestResponse(suggestions=[suggested(phone, asked)], care_note="Please see a doctor.")
    assert any("care note" in p for p in check_invariants(asked, calm))


def test_eval_notices_a_wrong_expectation(db):
    phone = next(case for case in CASES if case.id == "phone_text")
    assert run_case(phone, db) == []

    wrong = replace(phone, expect_roadblocks={R.OVERLOAD: "strong"})
    assert any("roadblocks expected" in p for p in run_case(wrong, db))

    wrong_safety = replace(phone, expect_safety=True)
    assert any("safety expected" in p for p in run_case(wrong_safety, db))
