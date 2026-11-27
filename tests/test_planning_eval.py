from app.evals import planning


def test_planning_eval_passes():
    result = planning.run()
    assert result.passed, result.failures
    assert result.golden_ok == result.golden_total
    assert result.tamper_caught == result.tamper_total
    assert result.sweep_days >= 1000


def test_main_prints_result_and_returns_zero(capsys):
    assert planning.main() == 0
    output = capsys.readouterr().out
    assert "RESULT: PASS" in output
    assert "Known gaps" in output


def test_eval_fails_if_the_validator_goes_blind(monkeypatch):
    """A gate that cannot fail is worthless: a validator that finds nothing must break the eval."""
    monkeypatch.setattr(planning, "validate_schedule", lambda *args, **kwargs: [])
    result = planning.run()
    assert not result.passed
    assert result.tamper_caught == 0
    assert planning.main() == 1


def test_eval_fails_if_the_planner_gives_wrong_answers(monkeypatch):
    real = planning.plan_day

    def forgetful(tasks, context, **kwargs):
        return real(tasks[:-1], context, **kwargs)  # silently loses the last task

    monkeypatch.setattr(planning, "plan_day", forgetful)
    result = planning.run()
    assert not result.passed
    assert result.golden_ok < result.golden_total
