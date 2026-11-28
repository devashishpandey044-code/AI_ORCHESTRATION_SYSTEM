"""Database work for the life intake and the obstacle list.

Rules that must hold whatever the caller does live here rather than in the routes:
the per-user cap on recorded problems, what a status change is allowed to do, and the
fact that an out-of-scope problem is frozen.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.intake_models import IntakeAnswer, Obstacle
from app.intake import questions
from app.intake.types import ObstacleStatus
from app.schemas.intake import IntakeProgress

# Nobody works on more than a handful of problems at once. The cap is high enough that
# an honest user never meets it and low enough that the list cannot be used as storage.
MAX_OBSTACLES = 50


class IntakeError(Exception):
    """A change the rules refuse. The route turns this into a 409."""


# --- intake answers ---


def upsert_answer(db: Session, user_id: uuid.UUID, question_key: str, value: str) -> IntakeAnswer:
    """Save one answer, replacing any earlier answer to the same question.

    The caller has already validated the value against its catalogue question.
    """
    row = db.scalar(
        select(IntakeAnswer).where(
            IntakeAnswer.user_id == user_id, IntakeAnswer.question_key == question_key
        )
    )
    if row is None:
        row = IntakeAnswer(user_id=user_id, question_key=question_key, value=value)
        db.add(row)
    else:
        row.value = value
    db.commit()
    db.refresh(row)
    return row


def list_answers(db: Session, user_id: uuid.UUID) -> list[IntakeAnswer]:
    """Every answer, in the order the intake asks the questions."""
    rows = list(db.scalars(select(IntakeAnswer).where(IntakeAnswer.user_id == user_id)))
    order = {key: index for index, key in enumerate(questions.keys())}
    # An answer whose question has since left the catalogue sorts last rather than vanishing.
    return sorted(rows, key=lambda row: (order.get(row.question_key, len(order)), row.question_key))


def progress(db: Session, user_id: uuid.UUID) -> IntakeProgress:
    answered = {row.question_key for row in list_answers(db, user_id)}
    missing = questions.missing_required(answered)
    return IntakeProgress(
        answered=len(answered),
        required_total=len(questions.required_keys()),
        missing_required=missing,
        complete=not missing,
    )


# --- obstacles ---


def create_obstacle(db: Session, user_id: uuid.UUID, text: str, severity: int | None) -> Obstacle:
    count = db.scalar(select(func.count(Obstacle.id)).where(Obstacle.user_id == user_id)) or 0
    if count >= MAX_OBSTACLES:
        raise IntakeError(
            f"You already have {MAX_OBSTACLES} problems recorded. "
            "Resolve or remove one before adding another."
        )
    row = Obstacle(user_id=user_id, text=text, severity=severity)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_obstacles(
    db: Session, user_id: uuid.UUID, status: ObstacleStatus | None = None
) -> list[Obstacle]:
    stmt = select(Obstacle).where(Obstacle.user_id == user_id)
    if status is not None:
        stmt = stmt.where(Obstacle.status == status)
    return list(db.scalars(stmt.order_by(Obstacle.created_at, Obstacle.id)))


def get_obstacle(db: Session, user_id: uuid.UUID, obstacle_id: uuid.UUID) -> Obstacle | None:
    # Scoped by user id: another user's problem looks exactly like a missing one.
    return db.scalar(
        select(Obstacle).where(Obstacle.id == obstacle_id, Obstacle.user_id == user_id)
    )


def update_obstacle(
    db: Session,
    obstacle: Obstacle,
    *,
    status: ObstacleStatus | None = None,
    severity: int | None = None,
) -> Obstacle:
    """Apply a change the user asked for.

    The schema has already refused the statuses a user may not set. This refuses the
    two moves the schema cannot see: changing a problem that is out of scope, and
    making a problem active before anything has classified it.
    """
    if obstacle.status is ObstacleStatus.OUT_OF_SCOPE:
        raise IntakeError(
            "This one is outside what the app advises on, so it cannot be changed here."
        )
    if status is ObstacleStatus.ACTIVE and obstacle.roadblock_type is None:
        raise IntakeError("This problem has not been classified yet, so it cannot be made active.")
    if severity is not None:
        obstacle.severity = severity
    if status is not None:
        obstacle.status = status
        obstacle.resolved_at = datetime.now(UTC) if status is ObstacleStatus.RESOLVED else None
    db.commit()
    db.refresh(obstacle)
    return obstacle


def delete_obstacle(db: Session, obstacle: Obstacle) -> None:
    """Remove a problem entirely. Deleting is the user's own data to do, out of scope or not."""
    db.delete(obstacle)
    db.commit()
