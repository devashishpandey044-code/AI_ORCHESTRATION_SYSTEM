"""Weekly review endpoint: the seven days ending on a date, summarised with suggestions.

Only days that have a check-in are counted. Suggestions come from fixed rules in code.
"""

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.checkins.schemas import WeeklyOut, to_weekly_out
from app.checkins.types import CheckinError
from app.checkins.weekly import review_week
from app.db.models import User
from app.db.session import get_db
from app.services.checkins import load_reports

router = APIRouter(prefix="/reviews", tags=["reviews"])

WINDOW_DAYS = 7


@router.get("/weekly", response_model=WeeklyOut)
def weekly_review(
    end: date,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> WeeklyOut:
    start = end - timedelta(days=WINDOW_DAYS - 1)
    try:
        reports = load_reports(db, user.id, start, end)
    except CheckinError as error:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "a stored check-in is damaged"
        ) from error
    return to_weekly_out(start, end, review_week(reports))
