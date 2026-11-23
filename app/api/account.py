from datetime import UTC, datetime

from fastapi import APIRouter, Response
from sqlalchemy import delete, select

from app.api.deps import CurrentUser, DbSession
from app.db.models import Goal, ScheduleConstraint
from app.schemas.account import UserExport
from app.schemas.constraint import ConstraintOut
from app.schemas.goal import GoalOut
from app.schemas.user import UserOut

router = APIRouter(prefix="/auth/me", tags=["account"])


@router.get("/export", response_model=UserExport)
def export_my_data(user: CurrentUser, db: DbSession) -> UserExport:
    goals = db.scalars(
        select(Goal).where(Goal.user_id == user.id).order_by(Goal.created_at, Goal.id)
    )
    constraints = db.scalars(
        select(ScheduleConstraint)
        .where(ScheduleConstraint.user_id == user.id)
        .order_by(ScheduleConstraint.created_at, ScheduleConstraint.id)
    )
    return UserExport(
        exported_at=datetime.now(UTC),
        user=UserOut.model_validate(user),
        goals=[GoalOut.model_validate(g) for g in goals],
        constraints=[ConstraintOut.model_validate(c) for c in constraints],
    )


@router.delete("", status_code=204)
def delete_my_account(user: CurrentUser, db: DbSession) -> Response:
    # Delete child rows explicitly. This does not rely on the database enforcing
    # ON DELETE CASCADE, so it behaves the same on Postgres and SQLite.
    db.execute(delete(Goal).where(Goal.user_id == user.id))
    db.execute(delete(ScheduleConstraint).where(ScheduleConstraint.user_id == user.id))
    db.delete(user)
    db.commit()
    return Response(status_code=204)
