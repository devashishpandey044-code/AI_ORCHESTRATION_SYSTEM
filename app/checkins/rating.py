"""Suggest a rating for a method experiment from check-in data. Pure code, no model call.

The idea: if plans were completed more often while a method was in use than in the days
just before it, the method probably helped. This only proposes a number. The user decides.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.checkins.compare import DayReport, percent
from app.checkins.types import CheckinError

BASELINE_DAYS = 14  # how far back "before the experiment" reaches
MIN_DAYS = 3  # usable days needed on each side
GAIN = 10  # percentage points
STRONG_GAIN = 20
CAVEAT = "This is a suggestion from your check-ins; other things may have changed too."


class RatingBasis(StrEnum):
    ENOUGH_DATA = "enough_data"
    NOT_ENOUGH_DURING = "not_enough_during"
    NOT_ENOUGH_BEFORE = "not_enough_before"


@dataclass(frozen=True)
class RatingSuggestion:
    rating: int | None
    basis: RatingBasis
    during_days: int
    before_days: int
    during_adherence: int | None
    before_adherence: int | None
    delta: int | None
    message: str


def window_adherence(reports: list[DayReport] | tuple[DayReport, ...]) -> tuple[int, int | None]:
    """(usable days, adherence percent). A usable day has planned minutes above 0."""
    if not isinstance(reports, (list, tuple)) or not all(
        isinstance(r, DayReport) for r in reports
    ):
        raise CheckinError("reports must be a list of DayReport values")
    usable = [r for r in reports if r.planned_minutes > 0]
    planned = sum(r.planned_minutes for r in usable)
    counted = sum(r.counted_minutes for r in usable)
    return len(usable), (percent(counted, planned) if planned else None)


def rating_for_delta(delta: int) -> int:
    if delta >= STRONG_GAIN:
        return 5
    if delta >= GAIN:
        return 4
    if delta > -GAIN:
        return 3
    if delta > -STRONG_GAIN:
        return 2
    return 1


def suggest_rating(
    during: list[DayReport] | tuple[DayReport, ...],
    before: list[DayReport] | tuple[DayReport, ...],
) -> RatingSuggestion:
    during_days, during_pct = window_adherence(during)
    before_days, before_pct = window_adherence(before)
    if during_days < MIN_DAYS:
        message = (
            f"Not enough check-ins yet: {during_days} usable day(s) during the experiment, "
            f"need {MIN_DAYS}."
        )
        return RatingSuggestion(
            None, RatingBasis.NOT_ENOUGH_DURING, during_days, before_days,
            during_pct, before_pct, None, message,
        )
    if before_days < MIN_DAYS:
        message = (
            f"No fair comparison yet: {before_days} usable day(s) in the {BASELINE_DAYS} days "
            f"before the experiment, need {MIN_DAYS}."
        )
        return RatingSuggestion(
            None, RatingBasis.NOT_ENOUGH_BEFORE, during_days, before_days,
            during_pct, before_pct, None, message,
        )
    assert during_pct is not None and before_pct is not None
    delta = during_pct - before_pct
    message = (
        f"{during_pct}% of your plan was completed during the experiment ({during_days} days) "
        f"versus {before_pct}% before it ({before_days} days): {delta:+d} points. {CAVEAT}"
    )
    return RatingSuggestion(
        rating_for_delta(delta), RatingBasis.ENOUGH_DATA, during_days, before_days,
        during_pct, before_pct, delta, message,
    )
