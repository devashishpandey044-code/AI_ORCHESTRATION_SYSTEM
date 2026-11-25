from app.evals.roadblocks import main, run_roadblock_eval
from app.evals.roadblocks_cases import RULE_CASES, VERIFY_CASES


def test_gate_cases_all_pass():
    report = run_roadblock_eval()
    assert report.rule_ok == report.rule_total == len(RULE_CASES), report.failures
    assert report.verify_ok == report.verify_total == len(VERIFY_CASES), report.failures


def test_case_ids_are_unique():
    ids = [case.id for case in RULE_CASES] + [case.id for case in VERIFY_CASES]
    assert len(ids) == len(set(ids))


def test_cli_exits_zero_when_gate_passes(capsys):
    assert main() == 0
    out = capsys.readouterr().out
    assert "RESULT: PASS" in out
    assert "rule cases correct" in out
