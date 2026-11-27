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
    UniqueConstraint,
    Uuid,
    func,
    text,
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


class LifeModelSource(enum.StrEnum):
    ONBOARDING = "onboarding"  # extracted from the onboarding conversation, user-confirmed
    USER_EDIT = "user_edit"  # the user changed it directly
    SYSTEM = "system"  # reserved for later automated updates


class LifeModelVersion(Base):
    """Immutable snapshot of a user's Life Model. The current model is the highest version."""

    __tablename__ = "life_model_versions"
    __table_args__ = (UniqueConstraint("user_id", "version", name="uq_life_model_user_version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    source: Mapped[LifeModelSource] = mapped_column(_enum(LifeModelSource))
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LLMCall(Base):
    """Metadata for each model call. Deliberately stores NO prompt or response text."""

    __tablename__ = "llm_calls"
    __table_args__ = (Index("ix_llm_calls_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    purpose: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    latency_ms: Mapped[float] = mapped_column(Float)
    success: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SafetyEvent(Base):
    """Anonymous record that the safety check fired. Deliberately NO user id and NO text."""

    __tablename__ = "safety_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    surface: Mapped[str] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(32))
    rule_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExperimentStatus(enum.StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class MethodExperiment(Base):
    """One attempt by a user at one method for one roadblock. Structured fields only."""

    __tablename__ = "method_experiments"
    __table_args__ = (
        CheckConstraint("rating IS NULL OR (rating BETWEEN 1 AND 5)", name="ck_experiments_rating"),
        Index("ix_experiments_user_status", "user_id", "status"),
        # A user may try a method again later, but never twice at the same time.
        Index(
            "uq_experiments_one_active_per_method",
            "user_id",
            "method_slug",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    # Not a foreign key: methods live in files, so a slug can outlive its method.
    method_slug: Mapped[str] = mapped_column(String(60))
    roadblock: Mapped[str] = mapped_column(String(32))
    status: Mapped[ExperimentStatus] = mapped_column(
        _enum(ExperimentStatus), default=ExperimentStatus.ACTIVE
    )
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# Keep last: registers the plan tables on Base.metadata.
from app.db import plan_models  # noqa: E402, F401
