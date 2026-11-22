import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import select, update

from app.api.deps import CurrentUser, DbSession
from app.db.models import HORIZON_ORDER, Goal, GoalHorizon, GoalStatus, User
from app.schemas.goal import GoalCreate, GoalOut, GoalUpdate

router = APIRouter(prefix="/goals", tags=["goals"])


def _get_owned_goal(db: DbSession, user: User, goal_id: uuid.UUID, label: str = "Goal") -> Goal:
    # Every query is scoped by user_id: another user's goal looks exactly like a missing one.
    goal = db.scalar(select(Goal).where(Goal.id == goal_id, Goal.user_id == user.id))
    if goal is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return goal


def _check_parent(
    db: DbSession, user: User, parent_id: uuid.UUID, child_horizon: GoalHorizon
) -> None:
    parent = _get_owned_goal(db, user, parent_id, label="Parent goal")
    if HORIZON_ORDER[child_horizon] <= HORIZON_ORDER[parent.horizon]:
        raise HTTPException(
            status_code=422,
            detail=f"A {child_horizon.value} goal cannot be nested under a "
            f"{parent.horizon.value} goal",
        )


@router.post("", response_model=GoalOut, status_code=201)
def create_goal(payload: GoalCreate, user: CurrentUser, db: DbSession) -> Goal:
    if payload.parent_id is not None:
        _check_parent(db, user, payload.parent_id, payload.horizon)
    goal = Goal(user_id=user.id, **payload.model_dump())
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


@router.get("", response_model=list[GoalOut])
def list_goals(
    user: CurrentUser,
    db: DbSession,
    horizon: GoalHorizon | None = None,
    status: GoalStatus | None = None,
    parent_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Goal]:
    stmt = select(Goal).where(Goal.user_id == user.id)
    if horizon is not None:
        stmt = stmt.where(Goal.horizon == horizon)
    if status is not None:
        stmt = stmt.where(Goal.status == status)
    if parent_id is not None:
        stmt = stmt.where(Goal.parent_id == parent_id)
    stmt = stmt.order_by(Goal.created_at, Goal.id).limit(limit).offset(offset)
    return list(db.scalars(stmt))


@router.get("/{goal_id}", response_model=GoalOut)
def get_goal(goal_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Goal:
    return _get_owned_goal(db, user, goal_id)


@router.patch("/{goal_id}", response_model=GoalOut)
def update_goal(goal_id: uuid.UUID, payload: GoalUpdate, user: CurrentUser, db: DbSession) -> Goal:
    goal = _get_owned_goal(db, user, goal_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("parent_id") is not None:
        _check_parent(db, user, changes["parent_id"], goal.horizon)
    for field, value in changes.items():
        setattr(goal, field, value)
    db.commit()
    db.refresh(goal)
    return goal


@router.post("/{goal_id}/review", response_model=GoalOut)
def mark_reviewed(goal_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Goal:
    """User confirms the goal is still valid. Feeds the 'goal lock-in' safeguard later."""
    goal = _get_owned_goal(db, user, goal_id)
    goal.last_reviewed_at = datetime.now(UTC)
    db.commit()
    db.refresh(goal)
    return goal


@router.delete("/{goal_id}", status_code=204)
def delete_goal(goal_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    goal = _get_owned_goal(db, user, goal_id)
    # Keep children; they simply become top-level (DB-agnostic, also works on SQLite tests).
    db.execute(update(Goal).where(Goal.parent_id == goal.id).values(parent_id=None))
    db.delete(goal)
    db.commit()
    return Response(status_code=204)
