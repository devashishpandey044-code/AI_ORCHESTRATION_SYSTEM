"""Request and response models for the check-in API. No database, no framework state."""

import uuid
from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.checkins.compare import DayReport
from app.checkins.patterns import Roadblock
from app.checkins.rating import RatingSuggestion
from app.checkins.types import BlockReason, Checkin, TaskOutcome, TaskStatus
from app.checkins.weekly import Suggestion, WeeklyReview

Minutes = Annotated[int, Field(strict=True, ge=0, le=1440)]
Energy = Annotated[int, Field(strict=True, ge=1, le=5)]


class OutcomeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: str = Field(min_length=1, max_length=200)
    status: TaskStatus
    actual_minutes: Minutes
    reason: BlockReason | None = None


class CheckinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcomes: list[OutcomeIn] = Field(max_length=50)
    energy: Energy | None = None
    note: str = Field(default="", max_length=500)


def to_checkin(request: CheckinRequest) -> Checkin:
    """Raises CheckinError for combinations the field rules cannot see (for example a
    skipped task without a reason, or a task reported twice)."""
    outcomes = tuple(
        TaskOutcome(o.task, o.status, o.actual_minutes, o.reason) for o in request.outcomes
    )
    return Checkin(outcomes, request.energy, request.note)


class TaskResultOut(BaseModel):
    task: str
    status: TaskStatus
    planned_minutes: int
    actual_minutes: int
    overrun_minutes: int
    reason: BlockReason | None


class ReportOut(BaseModel):
    planned_minutes: int
    counted_minutes: int
    overrun_minutes: int
    adherence_percent: int | None
    unreported: list[str]
    tasks: list[TaskResultOut]


class CheckinOut(BaseModel):
    date: date
    energy: int | None
    note: str
    report: ReportOut


def to_report_out(report: DayReport) -> ReportOut:
    return ReportOut(
        planned_minutes=report.planned_minutes,
        counted_minutes=report.counted_minutes,
        overrun_minutes=report.overrun_minutes,
        adherence_percent=report.adherence_percent,
        unreported=list(report.unreported),
        tasks=[
            TaskResultOut(
                task=r.key,
                status=r.status,
                planned_minutes=r.planned_minutes,
                actual_minutes=r.actual_minutes,
                overrun_minutes=r.overrun_minutes,
                reason=r.reason,
            )
            for r in report.results
        ],
    )


def to_checkin_out(plan_date: date, checkin: Checkin, report: DayReport) -> CheckinOut:
    return CheckinOut(
        date=plan_date, energy=checkin.energy, note=checkin.note, report=to_report_out(report)
    )


class RoadblockOut(BaseModel):
    reason: BlockReason
    occurrences: int
    days_affected: int
    minutes_lost: int
    share_percent: int


class SuggestionOut(BaseModel):
    code: str
    message: str
    value: int | None


class WeeklyOut(BaseModel):
    start: date
    end: date
    days_with_checkins: int
    planned_minutes: int
    counted_minutes: int
    adherence_percent: int | None
    estimate_ratio_percent: int | None
    unreported_percent: int | None
    roadblocks: list[RoadblockOut]
    suggestions: list[SuggestionOut]


def _roadblock_out(r: Roadblock) -> RoadblockOut:
    return RoadblockOut(
        reason=r.reason,
        occurrences=r.occurrences,
        days_affected=r.days_affected,
        minutes_lost=r.minutes_lost,
        share_percent=r.share_percent,
    )


def _suggestion_out(s: Suggestion) -> SuggestionOut:
    return SuggestionOut(code=s.code.value, message=s.message, value=s.value)


def to_weekly_out(start: date, end: date, review: WeeklyReview) -> WeeklyOut:
    return WeeklyOut(
        start=start,
        end=end,
        days_with_checkins=review.days,
        planned_minutes=review.planned_minutes,
        counted_minutes=review.counted_minutes,
        adherence_percent=review.adherence_percent,
        estimate_ratio_percent=review.patterns.estimate_ratio_percent,
        unreported_percent=review.patterns.unreported_percent,
        roadblocks=[_roadblock_out(r) for r in review.patterns.roadblocks],
        suggestions=[_suggestion_out(s) for s in review.suggestions],
    )


class RatingSuggestionOut(BaseModel):
    experiment_id: uuid.UUID
    during_from: date
    during_to: date
    before_from: date
    before_to: date
    rating: int | None
    basis: str
    during_days: int
    before_days: int
    during_adherence: int | None
    before_adherence: int | None
    delta: int | None
    message: str


def to_rating_out(
    experiment_id: uuid.UUID,
    during: tuple[date, date],
    before: tuple[date, date],
    suggestion: RatingSuggestion,
) -> RatingSuggestionOut:
    return RatingSuggestionOut(
        experiment_id=experiment_id,
        during_from=during[0],
        during_to=during[1],
        before_from=before[0],
        before_to=before[1],
        rating=suggestion.rating,
        basis=suggestion.basis.value,
        during_days=suggestion.during_days,
        before_days=suggestion.before_days,
        during_adherence=suggestion.during_adherence,
        before_adherence=suggestion.before_adherence,
        delta=suggestion.delta,
        message=suggestion.message,
    )
