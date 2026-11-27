import pytest

from app.checkins.compare import compare_day
from app.checkins.types import BlockReason, Checkin, CheckinError, TaskOutcome, TaskStatus
from app.checkins.weekly import SuggestionCode as C
from app.checkins.weekly import review_week

D, P, S = TaskStatus.DONE, TaskStatus.PARTIAL, TaskStatus.SKIPPED


def day(planned, *outcomes):
    return compare_day(planned, Checkin(tuple(outcomes)))


def codes(review):
    return [s.code for s in review.suggestions]


def test_too_few_days():
    r = review_week([day({"a": 30}, TaskOutcome("a", D, 30))])
    assert codes(r) == [C.NEED_MORE_DATA]
    assert r.suggestions[0].value == 1
    assert "1 day" in r.suggestions[0].message


def test_empty_week():
    r = review_week([])
    assert codes(r) == [C.NEED_MORE_DATA] and r.adherence_percent is None


def test_keep_going_when_all_done():
    d = day({"a": 30}, TaskOutcome("a", D, 30))
    r = review_week([d, d, d])
    assert codes(r) == [C.KEEP_GOING] and r.adherence_percent == 100
    assert r.suggestions[0].value == 100


def test_plan_less_when_low_adherence():
    d = day({"a": 60}, TaskOutcome("a", P, 15, BlockReason.OTHER))
    r = review_week([d, d, d])
    assert r.adherence_percent == 25
    plan = next(s for s in r.suggestions if s.code is C.PLAN_LESS)
    assert plan.value == 50 and "50%" in plan.message


def test_plan_less_target_is_adherence_plus_ten():
    d = day({"a": 100}, TaskOutcome("a", P, 55, BlockReason.OTHER))
    r = review_week([d, d, d])
    assert next(s for s in r.suggestions if s.code is C.PLAN_LESS).value == 65


def test_longer_estimates_from_ratio():
    d = day({"a": 40}, TaskOutcome("a", D, 60))
    r = review_week([d, d, d])
    longer = next(s for s in r.suggestions if s.code is C.LONGER_ESTIMATES)
    assert longer.value == 150
    assert C.KEEP_GOING in codes(r)


def test_roadblock_reasons_map_to_suggestions_in_fixed_order():
    d = day(
        {"a": 30, "b": 30, "c": 30},
        TaskOutcome("a", S, 0, BlockReason.TOO_TIRED),
        TaskOutcome("b", S, 0, BlockReason.INTERRUPTED),
        TaskOutcome("c", S, 0, BlockReason.LOST_MOTIVATION),
    )
    r = review_week([d, d, d])
    assert codes(r) == [C.PLAN_LESS, C.PROTECT_ENERGY, C.ADD_BUFFER, C.SMALLER_STARTS]


def test_interrupted_and_unplanned_share_one_suggestion():
    d = day(
        {"a": 30, "b": 30},
        TaskOutcome("a", S, 0, BlockReason.INTERRUPTED),
        TaskOutcome("b", S, 0, BlockReason.UNPLANNED_EVENT),
    )
    r = review_week([d, d, d])
    assert codes(r).count(C.ADD_BUFFER) == 1


def test_other_reason_gives_no_specific_suggestion():
    d = day({"a": 30}, TaskOutcome("a", S, 0, BlockReason.OTHER))
    r = review_week([d, d, d])
    assert codes(r) == [C.PLAN_LESS]


def test_report_more_when_many_unreported():
    d = day({"a": 30, "b": 30}, TaskOutcome("a", D, 30))
    r = review_week([d, d, d])
    assert C.REPORT_MORE in codes(r) and C.KEEP_GOING not in codes(r)
    assert r.suggestions[0].value == 50


def test_no_keep_going_with_roadblock():
    good = day({"a": 270}, TaskOutcome("a", D, 270))
    blocked = day({"b": 10}, TaskOutcome("b", S, 0, BlockReason.TOO_TIRED))
    r = review_week([good, blocked, blocked, blocked])
    assert r.adherence_percent >= 85
    assert C.KEEP_GOING not in codes(r) and C.PROTECT_ENERGY in codes(r)


def test_totals():
    d1 = day({"a": 30}, TaskOutcome("a", D, 30))
    d2 = day({"b": 60}, TaskOutcome("b", P, 30, BlockReason.OTHER))
    r = review_week([d1, d2, d1])
    assert r.planned_minutes == 120 and r.counted_minutes == 90 and r.days == 3
    assert r.adherence_percent == 75


def test_same_input_same_output():
    d = day({"a": 30}, TaskOutcome("a", S, 0, BlockReason.TOO_TIRED))
    assert review_week([d, d, d]) == review_week([d, d, d])


def test_bad_input_rejected():
    with pytest.raises(CheckinError):
        review_week([1, 2, 3])
    with pytest.raises(CheckinError):
        review_week("abc")
