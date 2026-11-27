"""Weekly review: summarise several days and suggest changes. Rules in code, no model call.

Suggestions come from fixed thresholds so they are explainable and testable.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.checkins.compare import DayReport, percent
from app.checkins.patterns import PatternReport, analyze
from app.checkins.types import BlockReason

MIN_DAYS_FOR_REVIEW = 3
LOW_ADHERENCE = 60
HIGH_ADHERENCE = 85
HIGH_UNREPORTED = 30
OVER_ESTIMATE = 125
MIN_PLAN_TARGET = 50


class SuggestionCode(StrEnum):
    NEED_MORE_DATA = "need_more_data"
    REPORT_MORE = "report_more"
    PLAN_LESS = "plan_less"
    LONGER_ESTIMATES = "longer_estimates"
    PROTECT_ENERGY = "protect_energy"
    ADD_BUFFER = "add_buffer"
    SMALLER_STARTS = "smaller_starts"
    KEEP_GOING = "keep_going"


# Fixed display order.
_ORDER = {code: i for i, code in enumerate(SuggestionCode)}

_REASON_TO_CODE = {
    BlockReason.TOO_TIRED: SuggestionCode.PROTECT_ENERGY,
    BlockReason.INTERRUPTED: SuggestionCode.ADD_BUFFER,
    BlockReason.UNPLANNED_EVENT: SuggestionCode.ADD_BUFFER,
    BlockReason.UNDERESTIMATED: SuggestionCode.LONGER_ESTIMATES,
    BlockReason.LOST_MOTIVATION: SuggestionCode.SMALLER_STARTS,
}


@dataclass(frozen=True)
class Suggestion:
    code: SuggestionCode
    message: str
    value: int | None = None  # the number the message is based on, if any


@dataclass(frozen=True)
class WeeklyReview:
    days: int
    planned_minutes: int
    counted_minutes: int
    adherence_percent: int | None
    patterns: PatternReport
    suggestions: tuple[Suggestion, ...]


def _message(code: SuggestionCode, value: int | None) -> str:
    return {
        SuggestionCode.NEED_MORE_DATA: (
            f"Only {value} day(s) of check-ins so far. Check in on at least "
            f"{MIN_DAYS_FOR_REVIEW} days to get a weekly review."
        ),
        SuggestionCode.REPORT_MORE: (
            f"{value}% of planned tasks were never reported, so this review may be off. "
            "Try a quick check-in each evening."
        ),
        SuggestionCode.PLAN_LESS: (
            f"Plan about {value}% of this week's workload next week. "
            "A smaller plan you finish beats a big one you drop."
        ),
        SuggestionCode.LONGER_ESTIMATES: (
            f"Finished tasks took {value}% of the planned time. Add time to your estimates."
        ),
        SuggestionCode.PROTECT_ENERGY: (
            "Being too tired keeps costing you tasks. Put hard tasks in your best hours "
            "and protect your sleep."
        ),
        SuggestionCode.ADD_BUFFER: (
            "Interruptions and surprise events keep eating your plan. Leave open buffer time."
        ),
        SuggestionCode.SMALLER_STARTS: (
            "Motivation is dropping tasks. Start each one with a 10 minute first step."
        ),
        SuggestionCode.KEEP_GOING: (
            f"{value}% of the plan happened with no repeating roadblock. Keep the same setup."
        ),
    }[code]


def review_week(reports: list[DayReport] | tuple[DayReport, ...]) -> WeeklyReview:
    patterns = analyze(reports)  # also validates the input
    planned = sum(r.planned_minutes for r in reports)
    counted = sum(r.counted_minutes for r in reports)
    adherence = percent(counted, planned) if planned else None

    values: dict[SuggestionCode, int | None] = {}
    if len(reports) < MIN_DAYS_FOR_REVIEW:
        values[SuggestionCode.NEED_MORE_DATA] = len(reports)
    else:
        unreported = patterns.unreported_percent
        if unreported is not None and unreported >= HIGH_UNREPORTED:
            values[SuggestionCode.REPORT_MORE] = unreported
        if adherence is not None and adherence < LOW_ADHERENCE:
            target = min(100, max(MIN_PLAN_TARGET, adherence + 10))
            values[SuggestionCode.PLAN_LESS] = target
        ratio = patterns.estimate_ratio_percent
        if ratio is not None and ratio >= OVER_ESTIMATE:
            values[SuggestionCode.LONGER_ESTIMATES] = ratio
        for roadblock in patterns.roadblocks:
            code = _REASON_TO_CODE.get(roadblock.reason)
            if code is not None and code not in values:
                values[code] = None
        calm = (
            adherence is not None
            and adherence >= HIGH_ADHERENCE
            and not patterns.roadblocks
            and SuggestionCode.REPORT_MORE not in values
        )
        if calm:
            values[SuggestionCode.KEEP_GOING] = adherence

    suggestions = tuple(
        Suggestion(code, _message(code, value), value)
        for code, value in sorted(values.items(), key=lambda kv: _ORDER[kv[0]])
    )
    return WeeklyReview(len(reports), planned, counted, adherence, patterns, suggestions)
