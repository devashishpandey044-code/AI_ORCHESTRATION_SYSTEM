from app.evals.safety import classify, main, run_safety_eval
from app.evals.safety_cases import CASES


def test_gate_cases_all_pass():
    report = run_safety_eval()
    assert report.missed == 0
    assert report.false_positives == 0
    assert report.recall == 1.0
    # pin the size of the golden set so it cannot silently shrink
    assert report.caught == 26
    assert report.clean == 18


def test_known_gaps_behave_as_documented():
    """If a gap gets fixed, this fails: remove known_gap_kind and move it into the gate."""
    gaps = [case for case in CASES if case.known_gap_kind is not None]
    assert len(gaps) == 4
    for case in gaps:
        assert classify(case) == case.known_gap_kind, case.id


def test_case_ids_are_unique():
    ids = [case.id for case in CASES]
    assert len(ids) == len(set(ids))


def test_cli_exits_zero_when_gate_passes(capsys):
    assert main() == 0
    out = capsys.readouterr().out
    assert "RESULT: PASS" in out
    assert "recall 100%" in out
