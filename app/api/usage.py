"""The signed-in user's own model usage: volume, health, speed and estimated cost."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, DbSession
from app.services.usage import load_call_rows
from app.usage.schemas import UsageOut, to_usage_out
from app.usage.summary import UsageError, summarize

router = APIRouter(prefix="/usage", tags=["usage"])

MAX_DAYS = 90


@router.get("", response_model=UsageOut)
def usage_summary(
    user: CurrentUser,
    db: DbSession,
    days: Annotated[int, Query(ge=1, le=MAX_DAYS)] = 7,
) -> UsageOut:
    since = datetime.now(UTC) - timedelta(days=days)
    try:
        rows = load_call_rows(db, user.id, since)
    except UsageError as error:
        raise HTTPException(500, "a stored model-call record is damaged") from error
    return to_usage_out(days, since, summarize(rows))
