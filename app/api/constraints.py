import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import ValidationError
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.db.models import ConstraintKind, ScheduleConstraint, User
from app.schemas.constraint import ConstraintCreate, ConstraintOut, ConstraintUpdate

router = APIRouter(prefix="/constraints", tags=["constraints"])


def _get_owned(db: DbSession, user: User, constraint_id: uuid.UUID) -> ScheduleConstraint:
    row = db.scalar(
        select(ScheduleConstraint).where(
            ScheduleConstraint.id == constraint_id, ScheduleConstraint.user_id == user.id
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Constraint not found")
    return row


@router.post("", response_model=ConstraintOut, status_code=201)
def create_constraint(
    payload: ConstraintCreate, user: CurrentUser, db: DbSession
) -> ScheduleConstraint:
    row = ScheduleConstraint(user_id=user.id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("", response_model=list[ConstraintOut])
def list_constraints(
    user: CurrentUser,
    db: DbSession,
    kind: ConstraintKind | None = None,
    active: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ScheduleConstraint]:
    stmt = select(ScheduleConstraint).where(ScheduleConstraint.user_id == user.id)
    if kind is not None:
        stmt = stmt.where(ScheduleConstraint.kind == kind)
    if active is not None:
        stmt = stmt.where(ScheduleConstraint.active == active)
    stmt = stmt.order_by(ScheduleConstraint.created_at, ScheduleConstraint.id)
    return list(db.scalars(stmt.limit(limit).offset(offset)))


@router.get("/{constraint_id}", response_model=ConstraintOut)
def get_constraint(constraint_id: uuid.UUID, user: CurrentUser, db: DbSession):
    return _get_owned(db, user, constraint_id)


@router.patch("/{constraint_id}", response_model=ConstraintOut)
def update_constraint(
    constraint_id: uuid.UUID, payload: ConstraintUpdate, user: CurrentUser, db: DbSession
) -> ScheduleConstraint:
    row = _get_owned(db, user, constraint_id)
    changes = payload.model_dump(exclude_unset=True)

    # Re-validate the *merged* result so a PATCH can't produce an invalid constraint.
    merged = {
        "title": row.title,
        "kind": row.kind,
        "days_of_week": row.days_of_week,
        "start_time": row.start_time,
        "end_time": row.end_time,
        "max_minutes_per_day": row.max_minutes_per_day,
        "is_hard": row.is_hard,
        "active": row.active,
    } | changes
    try:
        ConstraintCreate(**merged)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=[{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()],
        ) from None

    for field, value in changes.items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{constraint_id}", status_code=204)
def delete_constraint(constraint_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    row = _get_owned(db, user, constraint_id)
    db.delete(row)
    db.commit()
    return Response(status_code=204)
