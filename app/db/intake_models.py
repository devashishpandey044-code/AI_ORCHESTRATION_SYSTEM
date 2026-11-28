"""Tables for the life intake and the obstacle list.

Two tables, and deliberately no more. Sleep and wake times, fixed commitments and
daily capacity limits already fit ScheduleConstraint, and goals already fit Goal, so
the intake writes into those rather than duplicating them.

An obstacle classifies into RoadblockType, the same taxonomy the methods library
matches on, so a stated problem can be matched to a method without a second taxonomy
to keep in step. A disclosure the app will not advise on is marked with the
OUT_OF_SCOPE status and keeps a null roadblock_type, so it can never match a method.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models import _enum
from app.intake.types import ObstacleSource, ObstacleStatus
from app.methods.taxonomy import RoadblockType


class IntakeAnswer(Base):
    """One answer to one intake question, kept in the user's own words.

    Stored verbatim as text whatever the question's kind, because this row is the
    source the extraction quotes from and the quote check verifies against. Parsing
    belongs to the schema layer, which knows each question's kind.
    """

    __tablename__ = "intake_answers"
    __table_args__ = (
        UniqueConstraint("user_id", "question_key", name="uq_intake_answers_user_question"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    # Not a foreign key: the catalogue lives in code, so a key can outlive its question.
    question_key: Mapped[str] = mapped_column(String(60))
    value: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Obstacle(Base):
    """A problem the user says is holding them back, in their own words."""

    __tablename__ = "obstacles"
    __table_args__ = (
        CheckConstraint(
            "severity IS NULL OR (severity BETWEEN 1 AND 5)", name="ck_obstacles_severity_range"
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_obstacles_confidence_range"
        ),
        # An out-of-scope obstacle must never carry a type, or method matching could
        # reach it. The boundary is enforced here as well as in the service.
        CheckConstraint(
            "status <> 'out_of_scope' OR roadblock_type IS NULL",
            name="ck_obstacles_out_of_scope_has_no_type",
        ),
        Index("ix_obstacles_user_status", "user_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text)
    roadblock_type: Mapped[RoadblockType | None] = mapped_column(
        _enum(RoadblockType), nullable=True
    )
    status: Mapped[ObstacleStatus] = mapped_column(
        _enum(ObstacleStatus), default=ObstacleStatus.STATED
    )
    source: Mapped[ObstacleSource] = mapped_column(
        _enum(ObstacleSource), default=ObstacleSource.STATED
    )
    severity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    classified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
