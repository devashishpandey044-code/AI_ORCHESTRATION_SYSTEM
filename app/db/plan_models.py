"""Tables for stored daily plans. Generated to match this project's id types.

plans: one row per user per day. plan_tasks: what was asked for and what happened to it.
plan_blocks: the finished timetable. Rows are always read and written through
app/services/plans.py, which scopes every query to one user.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base

MODES = "('full', 'minimum')"
KINDS = "('fixed', 'sleep', 'task', 'break', 'intervention')"
STATUSES = "('placed', 'unplaced', 'dropped')"
EFFORTS = "('light', 'focus')"


class Plan(Base):
    __tablename__ = "plans"
    __table_args__ = (
        UniqueConstraint("user_id", "plan_date", name="uq_plans_user_date"),
        CheckConstraint(f"mode IN {MODES}", name="ck_plans_mode"),
        CheckConstraint(
            "awake_start >= 0 AND awake_start < awake_end AND awake_end <= 1440",
            name="ck_plans_awake",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    plan_date: Mapped[date] = mapped_column(Date)
    mode: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(200))
    awake_start: Mapped[int] = mapped_column(Integer)
    awake_end: Mapped[int] = mapped_column(Integer)
    focus_capacity: Mapped[int] = mapped_column(Integer)
    max_focus_run: Mapped[int] = mapped_column(Integer)
    break_minutes: Mapped[int] = mapped_column(Integer)
    focus_minutes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlanTask(Base):
    __tablename__ = "plan_tasks"
    __table_args__ = (
        UniqueConstraint("plan_id", "key", name="uq_plan_tasks_plan_key"),
        CheckConstraint(f"status IN {STATUSES}", name="ck_plan_tasks_status"),
        CheckConstraint(f"effort IN {EFFORTS}", name="ck_plan_tasks_effort"),
        CheckConstraint("priority BETWEEN 1 AND 3", name="ck_plan_tasks_priority"),
        CheckConstraint("minutes BETWEEN 10 AND 240", name="ck_plan_tasks_minutes"),
        CheckConstraint(
            "planned_minutes IS NULL OR planned_minutes BETWEEN 10 AND 240",
            name="ck_plan_tasks_planned_minutes",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("plans.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(120))
    minutes: Mapped[int] = mapped_column(Integer)
    planned_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority: Mapped[int] = mapped_column(Integer)
    effort: Mapped[str] = mapped_column(String(8))
    goal_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("goals.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(12))
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)


class PlanBlock(Base):
    __tablename__ = "plan_blocks"
    __table_args__ = (
        CheckConstraint(f"kind IN {KINDS}", name="ck_plan_blocks_kind"),
        CheckConstraint(
            "start_minute >= 0 AND start_minute < end_minute AND end_minute <= 1440",
            name="ck_plan_blocks_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("plans.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(120))
    start_minute: Mapped[int] = mapped_column(Integer)
    end_minute: Mapped[int] = mapped_column(Integer)
    task_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
