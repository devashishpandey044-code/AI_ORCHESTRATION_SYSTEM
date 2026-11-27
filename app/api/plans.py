"""Plan endpoints: build, read and delete one day's plan for the signed-in user.

Building a plan runs the planner (no model call), stores it, and returns it. Reading a plan
re-validates it. A plan that belongs to another user is reported as not found.
"""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.planning.fallback import plan_day
from app.planning.records import StoredPlanCorrupt
from app.planning.schemas import PlanOut, PlanRequest, to_domain, to_response
from app.planning.validator import PlanInvalid
from app.services.plans import GoalNotFound, delete_day_plan, load_day_plan, save_day_plan

router = APIRouter(prefix="/plans", tags=["plans"])


@router.post("/{plan_date}", response_model=PlanOut)
def build_plan(
    plan_date: date,
    body: PlanRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> PlanOut:
    tasks, context, low_energy = to_domain(body)
    plan = plan_day(tasks, context, low_energy=low_energy)
    try:
        save_day_plan(db, user.id, plan_date, plan, tasks)
    except GoalNotFound as error:
        db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "goal not found") from error
    db.commit()
    return to_response(plan_date, plan)


@router.get("/{plan_date}", response_model=PlanOut)
def read_plan(
    plan_date: date,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> PlanOut:
    try:
        stored = load_day_plan(db, user.id, plan_date)
    except (PlanInvalid, StoredPlanCorrupt) as error:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "the stored plan is damaged"
        ) from error
    if stored is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no plan for that day")
    return to_response(plan_date, stored.day_plan)


@router.delete("/{plan_date}", status_code=status.HTTP_204_NO_CONTENT)
def remove_plan(
    plan_date: date,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    if not delete_day_plan(db, user.id, plan_date):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no plan for that day")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
