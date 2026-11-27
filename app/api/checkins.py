"""Check-in endpoints: report how a planned day went, read it back, or remove it.

Saving checks every reported task against that day's plan and returns the plan-versus-actual
report. A day or check-in that belongs to another user is reported as not found.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.checkins.records import StoredCheckinCorrupt
from app.checkins.schemas import CheckinOut, CheckinRequest, to_checkin, to_checkin_out
from app.checkins.types import CheckinError
from app.db.models import User
from app.db.session import get_db
from app.services.checkins import (
    PlanNotFoundForCheckin,
    delete_checkin,
    load_checkin,
    load_day_report,
    save_checkin,
)

router = APIRouter(prefix="/checkins", tags=["checkins"])

DAMAGED = "the stored check-in is damaged"


@router.put("/{plan_date}", response_model=CheckinOut)
def write_checkin(
    plan_date: date,
    body: CheckinRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> CheckinOut:
    try:
        checkin = to_checkin(body)
        save_checkin(db, user.id, plan_date, checkin)
    except PlanNotFoundForCheckin as error:
        db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no plan for that day") from error
    except CheckinError as error:
        db.rollback()
        raise HTTPException(422, str(error)) from error
    db.commit()
    report = load_day_report(db, user.id, plan_date)
    if report is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, DAMAGED)
    return to_checkin_out(plan_date, checkin, report)


@router.get("/{plan_date}", response_model=CheckinOut)
def read_checkin(
    plan_date: date,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> CheckinOut:
    try:
        checkin = load_checkin(db, user.id, plan_date)
        if checkin is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no check-in for that day")
        report = load_day_report(db, user.id, plan_date)
    except (StoredCheckinCorrupt, CheckinError) as error:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, DAMAGED) from error
    if report is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, DAMAGED)
    return to_checkin_out(plan_date, checkin, report)


@router.delete("/{plan_date}", status_code=status.HTTP_204_NO_CONTENT)
def remove_checkin(
    plan_date: date,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    if not delete_checkin(db, user.id, plan_date):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no check-in for that day")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
