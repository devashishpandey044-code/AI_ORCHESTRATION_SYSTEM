import enum
import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    Uuid,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _enum(enum_cls: type[enum.Enum]) -> Enum:
    # Stored as plain VARCHAR (not a native PG enum) so migrations stay simple.
    return Enum(
        enum_cls,
        native_enum=False,
        length=32,
        values_callable=lambda e: [m.value for m in e],
    )


class GoalHorizon(enum.StrEnum):
    VISION = "vision"
    MILESTONE = "milestone"
    WEEKLY = "weekly"
    DAILY = "daily"


# Lower number = higher in the hierarchy. A child must sit strictly below its parent.
HORIZON_ORDER: dict[GoalHorizon, int] = {
    GoalHorizon.VISION: 0,
    GoalHorizon.MILESTONE: 1,
    GoalHorizon.WEEKLY: 2,
    GoalHorizon.DAILY: 3,
}


class GoalStatus(enum.StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    DROPPED = "dropped"


class GoalSource(enum.StrEnum):
    STATED = "stated"  # the user said it
    INFERRED = "inferred"  # the model suggested it (never treated as fact)


class ConstraintKind(enum.StrEnum):
    FIXED_COMMITMENT = "fixed_commitment"  # classes, work shifts, etc.
    SLEEP = "sleep"  # may cross midnight
    CAPACITY_LIMIT = "capacity_limit"  # e.g. max deep-work minutes per day


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Goal(Base):
    __tablename__ = "goals"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_goals_confidence_range"),
        Index("ix_goals_user_horizon_status", "user_id", "horizon", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("goals.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    horizon: Mapped[GoalHorizon] = mapped_column(_enum(GoalHorizon))
    status: Mapped[GoalStatus] = mapped_column(_enum(GoalStatus), default=GoalStatus.ACTIVE)
    source: Mapped[GoalSource] = mapped_column(_enum(GoalSource), default=GoalSource.STATED)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ScheduleConstraint(Base):
    __tablename__ = "schedule_constraints"
    __table_args__ = (
        CheckConstraint(
            "max_minutes_per_day IS NULL OR (max_minutes_per_day BETWEEN 1 AND 1440)",
            name="ck_constraints_max_minutes_range",
        ),
        Index("ix_constraints_user_kind", "user_id", "kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[ConstraintKind] = mapped_column(_enum(ConstraintKind))
    days_of_week: Mapped[list[int]] = mapped_column(JSON, default=list)  # 0=Mon .. 6=Sun
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    max_minutes_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_hard: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
