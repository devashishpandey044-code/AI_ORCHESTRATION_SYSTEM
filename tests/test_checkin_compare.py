import pytest

from app.checkins.compare import compare_day, percent
from app.checkins.types import BlockReason, Checkin, CheckinError, TaskOutcome, TaskStatus

D, P, S = TaskStatus.DONE, TaskStatus.PARTIAL, TaskStatus.SKIPPED


def test_percent_rounds_half_up():
    assert percent(1, 2) == 50
    assert percent(1, 3) == 33
    assert percent(2, 3) == 67
    assert percent(1, 8) == 13
    assert percent(0, 5) == 0
    assert percent(5, 5) == 100


def test_all_done():
    r = compare_day({"a": 30, "b": 60}, Checkin((TaskOutcome("a", D, 30), TaskOutcome("b", D, 60))))
    assert r.adherence_percent == 100
    assert r.planned_minutes == 90 and r.counted_minutes == 90 and r.overrun_minutes == 0
    assert r.unreported == ()


def test_mixed_day():
    c = Checkin(
        (
            TaskOutcome("a", D, 30),
            TaskOutcome("b", P, 20, BlockReason.INTERRUPTED),
            TaskOutcome("c", S, 0, BlockReason.TOO_TIRED),
        )
    )
    r = compare_day({"a": 30, "b": 60, "c": 30}, c)
    assert r.counted_minutes == 50 and r.planned_minutes == 120
    assert r.adherence_percent == 42


def test_overrun_is_tracked_but_not_counted():
    r = compare_day({"a": 30}, Checkin((TaskOutcome("a", D, 50),)))
    assert r.counted_minutes == 30 and r.overrun_minutes == 20
    assert r.adherence_percent == 100
    assert r.results[0].overrun_minutes == 20


def test_unreported_tasks_listed_and_not_counted():
    r = compare_day({"a": 30, "b": 30}, Checkin((TaskOutcome("a", D, 30),)))
    assert r.unreported == ("b",)
    assert r.adherence_percent == 50


def test_unknown_task_rejected():
    with pytest.raises(CheckinError):
        compare_day({"a": 30}, Checkin((TaskOutcome("z", D, 30),)))


def test_empty_plan_has_no_adherence():
    r = compare_day({}, Checkin(()))
    assert r.adherence_percent is None and r.planned_minutes == 0


def test_empty_checkin_is_zero_percent():
    r = compare_day({"a": 30}, Checkin(()))
    assert r.adherence_percent == 0 and r.unreported == ("a",)


@pytest.mark.parametrize("bad", [{"a": 0}, {"a": -5}, {"a": 1.5}, {"a": True}, {1: 30}])
def test_bad_planned(bad):
    with pytest.raises(CheckinError):
        compare_day(bad, Checkin(()))


def test_results_sorted_by_key():
    c = Checkin((TaskOutcome("b", D, 10), TaskOutcome("a", D, 10)))
    r = compare_day({"a": 10, "b": 10}, c)
    assert [x.key for x in r.results] == ["a", "b"]
