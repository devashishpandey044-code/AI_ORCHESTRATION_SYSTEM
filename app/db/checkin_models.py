"""Tables for stored check-ins. Generated to match this project's id types.

checkins: at most one per stored plan (so one per user per day).
checkin_outcomes: how each planned task went. Rows are always read and written through
app/services/checkins.py, which scopes every query to one user.
"""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base

STATUSES = "('done', 'partial', 'skipped')"
REASONS = (
    "('too_tired', 'interrupted', 'underestimated', 'lost_motivation', "
    "'unplanned_event', 'other')"
)


class CheckinRow(Base):
    __tablename__ = "checkins"
    __table_args__ = (
        UniqueConstraint("plan_id", name="uq_checkins_plan"),
        CheckConstraint(
            "energy IS NULL OR (energy >= 1 AND energy <= 5)", name="ck_checkins_energy"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("plans.id", ondelete="CASCADE"))
    energy: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str] = mapped_column(String(500), default="")


class CheckinOutcomeRow(Base):
    __tablename__ = "checkin_outcomes"
    __table_args__ = (
        UniqueConstraint("checkin_id", "task_key", name="uq_checkin_outcomes_task"),
        CheckConstraint(f"status IN {STATUSES}", name="ck_checkin_outcomes_status"),
        CheckConstraint(
            f"reason IS NULL OR reason IN {REASONS}", name="ck_checkin_outcomes_reason"
        ),
        CheckConstraint(
            "actual_minutes >= 0 AND actual_minutes <= 1440", name="ck_checkin_outcomes_minutes"
        ),
        CheckConstraint(
            "status <> 'skipped' OR (actual_minutes = 0 AND reason IS NOT NULL)",
            name="ck_checkin_outcomes_skipped",
        ),
        CheckConstraint(
            "status = 'skipped' OR actual_minutes > 0", name="ck_checkin_outcomes_worked"
        ),
        CheckConstraint(
            "status <> 'done' OR reason IS NULL", name="ck_checkin_outcomes_done_reason"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    checkin_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("checkins.id", ondelete="CASCADE")
    )
    task_key: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16))
    actual_minutes: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
