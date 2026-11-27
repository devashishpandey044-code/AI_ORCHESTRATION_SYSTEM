import uuid
from datetime import date

import pytest

from app.checkins.compare import compare_day
from app.checkins.rating import (
    BASELINE_DAYS,
    MIN_DAYS,
    RatingBasis,
    rating_for_delta,
    suggest_rating,
    window_adherence,
)
from app.checkins.schemas import to_rating_out
from app.checkins.types import BlockReason, Checkin, CheckinError, TaskOutcome, TaskStatus

D, S = TaskStatus.DONE, TaskStatus.SKIPPED


def day(done_minutes, planned=100):
    """A day with one task of `planned` minutes of which `done_minutes` were done."""
    if done_minutes == 0:
        outcome = TaskOutcome("a", S, 0, BlockReason.OTHER)
    else:
        outcome = TaskOutcome("a", TaskStatus.PARTIAL, done_minutes)
    return compare_day({"a": planned}, Checkin((outcome,)))


def days(percent_done, count):
    return [day(percent_done)] * count


@pytest.mark.parametrize(
    "delta,rating",
    [(100, 5), (20, 5), (19, 4), (10, 4), (9, 3), (0, 3), (-9, 3), (-10, 2), (-19, 2),
     (-20, 1), (-100, 1)],
)
def test_rating_for_delta_edges(delta, rating):
    assert rating_for_delta(delta) == rating


def test_window_adherence():
    assert window_adherence([]) == (0, None)
    assert window_adherence(days(50, 4)) == (4, 50)
    mixed = [day(100), day(0)]
    assert window_adherence(mixed) == (2, 50)


def test_days_without_planned_minutes_are_not_usable():
    empty = compare_day({}, Checkin(()))
    assert window_adherence([empty, day(100)]) == (1, 100)


def test_window_adherence_rejects_bad_input():
    with pytest.raises(CheckinError):
        window_adherence("nope")
    with pytest.raises(CheckinError):
        window_adherence([1])


def test_big_improvement():
    s = suggest_rating(days(90, 4), days(40, 5))
    assert s.rating == 5 and s.basis is RatingBasis.ENOUGH_DATA
    assert (s.during_adherence, s.before_adherence, s.delta) == (90, 40, 50)
    assert "+50 points" in s.message and "suggestion" in s.message


def test_small_improvement_no_change_small_drop_big_drop():
    assert suggest_rating(days(60, 3), days(50, 3)).rating == 4
    assert suggest_rating(days(55, 3), days(50, 3)).rating == 3
    assert suggest_rating(days(45, 3), days(60, 3)).rating == 2
    assert suggest_rating(days(30, 3), days(70, 3)).rating == 1


def test_not_enough_during():
    s = suggest_rating(days(90, MIN_DAYS - 1), days(40, 5))
    assert s.rating is None and s.basis is RatingBasis.NOT_ENOUGH_DURING
    assert s.delta is None and "need 3" in s.message


def test_not_enough_before():
    s = suggest_rating(days(90, 5), days(40, MIN_DAYS - 1))
    assert s.rating is None and s.basis is RatingBasis.NOT_ENOUGH_BEFORE
    assert str(BASELINE_DAYS) in s.message


def test_during_is_checked_first():
    s = suggest_rating([], [])
    assert s.basis is RatingBasis.NOT_ENOUGH_DURING


def test_exactly_enough_days_is_enough():
    s = suggest_rating(days(80, MIN_DAYS), days(50, MIN_DAYS))
    assert s.rating == 5 and s.during_days == MIN_DAYS


def test_same_input_same_output():
    assert suggest_rating(days(80, 4), days(50, 4)) == suggest_rating(days(80, 4), days(50, 4))


def test_schema_output():
    s = suggest_rating(days(90, 4), days(40, 5))
    eid = uuid.uuid4()
    out = to_rating_out(eid, (date(2026, 11, 23), date(2026, 11, 28)),
                        (date(2026, 11, 9), date(2026, 11, 22)), s)
    data = out.model_dump(mode="json")
    assert data["experiment_id"] == str(eid) and data["rating"] == 5
    assert data["basis"] == "enough_data" and data["delta"] == 50
    assert data["during_from"] == "2026-11-23" and data["before_to"] == "2026-11-22"
