from app.evals.grounding import evaluate_case, main, run_grounding_eval
from app.evals.grounding_cases import CASES
from app.schemas.life_model import LifeModelData


def test_gate_cases_all_pass():
    report = run_grounding_eval()
    assert report.missed == 0
    assert report.false_downgrades == 0
    assert report.catch_rate == 1.0
    assert report.false_downgrade_rate == 0.0
    # sanity check on the size of the golden set, so it cannot silently shrink
    assert report.caught == 4
    assert report.kept == 10


def test_known_gaps_behave_as_documented():
    """If a gap gets fixed, this fails: move that case into the gate by removing known_gap_kind."""
    gaps = [case for case in CASES if case.known_gap_kind is not None]
    assert len(gaps) == 3
    for case in gaps:
        kinds = {outcome.kind for outcome in evaluate_case(case)}
        assert kinds == {case.known_gap_kind}, case.id


def test_every_case_is_valid_life_model_data():
    for case in CASES:
        LifeModelData.model_validate(case.model_output)


def test_case_ids_are_unique():
    ids = [case.id for case in CASES]
    assert len(ids) == len(set(ids))


def test_cli_exits_zero_when_gate_passes(capsys):
    assert main() == 0
    out = capsys.readouterr().out
    assert "RESULT: PASS" in out
    assert "catch rate 100%" in out
