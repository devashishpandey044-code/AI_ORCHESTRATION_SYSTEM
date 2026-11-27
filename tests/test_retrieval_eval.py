from app.evals.retrieval import main, run_retrieval_eval
from app.evals.retrieval_cases import CASES
from app.retrieval.demo import main as demo_main


def test_gate_cases_all_pass():
    report = run_retrieval_eval()
    assert report.total == len(CASES)
    assert report.top3 == report.total, report.misses


def test_case_ids_are_unique():
    ids = [case.id for case in CASES]
    assert len(ids) == len(set(ids))


def test_cli_exits_zero_when_gate_passes(capsys):
    assert main() == 0
    out = capsys.readouterr().out
    assert "RESULT: PASS" in out
    assert "expected method in top 3" in out


def test_demo_prints_results(capsys):
    code = demo_main(["--roadblocks", "distraction", "--text", "my phone keeps buzzing"])
    assert code == 0
    assert "phone_friction" in capsys.readouterr().out
