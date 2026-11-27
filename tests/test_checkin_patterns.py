import pytest

from app.checkins.compare import compare_day
from app.checkins.patterns import analyze
from app.checkins.types import BlockReason, Checkin, CheckinError, TaskOutcome, TaskStatus

D, P, S = TaskStatus.DONE, TaskStatus.PARTIAL, TaskStatus.SKIPPED
TIRED, INT = BlockReason.TOO_TIRED, BlockReason.INTERRUPTED


def day(planned, *outcomes):
    return compare_day(planned, Checkin(tuple(outcomes)))


def tired_skip(key="a"):
    return TaskOutcome(key, S, 0, TIRED)


def test_no_reports():
    r = analyze([])
    assert r.days == 0 and r.roadblocks == ()
    assert r.estimate_ratio_percent is None and r.unreported_percent is None


def test_pattern_needs_enough_occurrences_and_days():
    days = [day({"a": 30}, tired_skip()), day({"a": 30}, tired_skip())]
    assert analyze(days).roadblocks == ()  # only 2 occurrences
    days.append(day({"a": 30}, tired_skip()))
    rb = analyze(days).roadblocks
    assert len(rb) == 1 and rb[0].reason is TIRED
    assert rb[0].occurrences == 3 and rb[0].days_affected == 3 and rb[0].minutes_lost == 90
    assert rb[0].share_percent == 100


def test_three_times_on_one_day_is_not_a_pattern():
    one_day = day(
        {"a": 10, "b": 10, "c": 10}, tired_skip("a"), tired_skip("b"), tired_skip("c")
    )
    assert analyze([one_day]).roadblocks == ()
    assert len(analyze([one_day], min_days=1).roadblocks) == 1


def test_minutes_lost_for_partial():
    d = day({"a": 60}, TaskOutcome("a", P, 20, INT))
    rb = analyze([d, d, d]).roadblocks
    assert rb[0].minutes_lost == 120 and rb[0].reason is INT


def test_ranked_by_minutes_lost_then_shares_sum():
    d1 = day({"a": 60, "b": 10}, tired_skip("a"), TaskOutcome("b", S, 0, INT))
    rb = analyze([d1, d1, d1]).roadblocks
    assert [r.reason for r in rb] == [TIRED, INT]
    assert rb[0].share_percent == 86 and rb[1].share_percent == 14


def test_estimate_ratio_uses_done_tasks_only():
    d1 = day({"a": 30, "b": 60}, TaskOutcome("a", D, 45), TaskOutcome("b", P, 10, INT))
    r = analyze([d1])
    assert r.estimate_ratio_percent == 150


def test_underestimate_not_blocking():
    d1 = day({"a": 30}, TaskOutcome("a", D, 45))
    assert analyze([d1, d1, d1]).roadblocks == ()


def test_unreported_percent():
    d1 = day({"a": 30, "b": 30}, TaskOutcome("a", D, 30))
    assert analyze([d1]).unreported_percent == 50


def test_deterministic_tie_break():
    d1 = day({"a": 30, "b": 30}, TaskOutcome("a", S, 0, INT), TaskOutcome("b", S, 0, TIRED))
    rb = analyze([d1, d1, d1]).roadblocks
    assert [r.reason for r in rb] == [INT, TIRED]  # equal loss: sorted by reason value


@pytest.mark.parametrize("bad", [0, -1, 1.5, True, "3", None])
def test_bad_thresholds(bad):
    with pytest.raises(CheckinError):
        analyze([], min_occurrences=bad)
    with pytest.raises(CheckinError):
        analyze([], min_days=bad)


def test_bad_reports():
    with pytest.raises(CheckinError):
        analyze("nope")
    with pytest.raises(CheckinError):
        analyze([1, 2])
