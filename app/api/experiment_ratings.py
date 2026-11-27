"""Suggested rating for a method experiment, from the user's own check-ins.

Compares plan completion during the experiment with the days just before it. It only
suggests a number: ending the experiment and rating it stay the user's own actions.
"""

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.checkins.rating import BASELINE_DAYS, suggest_rating
from app.checkins.schemas import RatingSuggestionOut, to_rating_out
from app.checkins.types import CheckinError
from app.db.models import MethodExperiment
from app.services.checkins import load_reports

router = APIRouter(prefix="/methods/experiments", tags=["methods"])


@router.get("/{experiment_id}/suggested-rating", response_model=RatingSuggestionOut)
def suggested_rating(
    experiment_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    through: date | None = None,
) -> RatingSuggestionOut:
    experiment = db.scalar(
        select(MethodExperiment).where(
            MethodExperiment.id == experiment_id, MethodExperiment.user_id == user.id
        )
    )
    if experiment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "experiment not found")
    start = experiment.started_at.date()
    end = through or (experiment.ended_at.date() if experiment.ended_at else None)
    if end is None:
        raise HTTPException(
            422, "the experiment is still running: pass through=YYYY-MM-DD to say how far to look"
        )
    if end < start:
        raise HTTPException(422, "through must not be before the experiment started")
    before = (start - timedelta(days=BASELINE_DAYS), start - timedelta(days=1))
    try:
        during_reports = load_reports(db, user.id, start, end)
        before_reports = load_reports(db, user.id, before[0], before[1])
    except CheckinError as error:
        raise HTTPException(500, "a stored check-in is damaged") from error
    suggestion = suggest_rating(during_reports, before_reports)
    return to_rating_out(experiment_id, (start, end), before, suggestion)
