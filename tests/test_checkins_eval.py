from app.evals import checkins as ev


def test_the_eval_passes():
    result = ev.run()
    assert result.passed, result.failures[:5]


def test_every_golden_and_tampering_case_is_right():
    result = ev.run()
    assert result.golden_days[0] == result.golden_days[1] > 0
    assert result.golden_weeks[0] == result.golden_weeks[1] > 0
    assert result.tampering[0] == result.tampering[1] > 0


def test_the_sweep_is_big_and_repeatable():
    first, second = ev.run(), ev.run()
    assert first.sweep_days >= 1000 and first.sweep_weeks >= 100
    assert (first.golden_days, first.golden_weeks, first.tampering, first.failures) == (
        second.golden_days,
        second.golden_weeks,
        second.tampering,
        second.failures,
    )


def test_main_prints_a_verdict_and_returns_zero(capsys):
    assert ev.main() == 0
    out = capsys.readouterr().out
    assert "Check-in eval" in out and "RESULT: PASS" in out
    assert "Known gaps" in out


def test_the_eval_fails_when_a_rule_is_broken(monkeypatch):
    monkeypatch.setattr("app.checkins.weekly.LOW_ADHERENCE", 30)
    result = ev.run()
    assert not result.passed


def test_the_eval_fails_when_rounding_is_broken(monkeypatch):
    monkeypatch.setattr("app.checkins.compare.percent", lambda part, whole: (100 * part) // whole)
    monkeypatch.setattr("app.checkins.weekly.percent", lambda part, whole: (100 * part) // whole)
    assert not ev.run().passed
