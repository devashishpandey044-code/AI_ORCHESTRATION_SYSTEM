from app.evals import report as report_module
from app.evals.report import EvalRun, render, run_eval


def _ok():
    print("Fake eval")
    print("  cases correct : 3/3   ")
    print()
    print("RESULT: PASS")
    return 0


def _bad():
    print("RESULT: FAIL")
    return 1


def _crash():
    print("partial output")
    raise RuntimeError("boom")


def test_output_is_captured_and_cleaned():
    run = run_eval("Fake", "does a thing", _ok)
    assert run.passed
    assert run.lines == ("Fake eval", "  cases correct : 3/3", "RESULT: PASS")


def test_a_failing_eval_is_reported_as_failing():
    assert run_eval("Bad", "x", _bad).passed is False


def test_a_crash_is_a_failure_and_keeps_what_was_printed():
    run = run_eval("Crash", "x", _crash)
    assert run.passed is False
    assert "partial output" in run.lines
    assert any(line.startswith("CRASH:") for line in run.lines)


def test_render_has_a_table_a_section_per_eval_and_the_limits():
    runs = [EvalRun("A", "first", True, ("RESULT: PASS",)), EvalRun("B", "second", False, ())]
    text = render(runs)
    assert "**1 of 2 evals pass.**" in text
    assert "| A | first | PASS |" in text
    assert "| B | second | FAIL |" in text
    assert "## A" in text and "## B" in text
    assert "## What this does not prove" in text


def test_render_is_the_same_every_time():
    runs = [EvalRun("A", "first", True, ("RESULT: PASS",))]
    assert render(runs) == render(runs)


def _patch_runs(monkeypatch, passed):
    runs = [EvalRun("A", "first", passed, ("RESULT: PASS",))]
    monkeypatch.setattr(report_module, "run_all", lambda: runs)


def test_check_fails_when_the_file_is_missing_or_stale(monkeypatch, tmp_path):
    _patch_runs(monkeypatch, True)
    path = tmp_path / "eval-report.md"
    assert report_module.main(["--check"], path) == 1
    path.write_text("old", encoding="utf-8")
    assert report_module.main(["--check"], path) == 1


def test_write_then_check_passes(monkeypatch, tmp_path):
    _patch_runs(monkeypatch, True)
    path = tmp_path / "eval-report.md"
    assert report_module.main(["--write"], path) == 0
    assert report_module.main(["--check"], path) == 0


def test_check_fails_when_an_eval_fails_even_if_the_file_matches(monkeypatch, tmp_path):
    _patch_runs(monkeypatch, False)
    path = tmp_path / "eval-report.md"
    report_module.main(["--write"], path)
    assert report_module.main(["--check"], path) == 1
