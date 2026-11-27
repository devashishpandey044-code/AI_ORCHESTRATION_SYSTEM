"""Storing and loading daily plans. Every query is scoped to one user.

The conversion between a plan and its rows lives in app/planning/records.py (plain Python,
fully tested without a database). This module only copies those rows in and out of the tables.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import Goal
from app.db.plan_models import Plan, PlanBlock, PlanTask
from app.planning.fallback import DayPlan
from app.planning.intervals import format_hhmm
from app.planning.records import (
    BLOCK_FIELDS,
    PLAN_FIELDS,
    TASK_FIELDS,
    StoredPlan,
    StoredRows,
    plan_to_rows,
    rows_to_plan,
)
from app.planning.types import PlanError, TaskSpec


class GoalNotFound(PlanError):
    """A task points at a goal that does not exist for this user."""


def _plain(value: Any) -> Any:
    return str(value) if isinstance(value, uuid.UUID) else value


def _require_own_goals(session: Session, user_id: Any, task_rows: tuple[dict, ...]) -> None:
    wanted = {row["goal_id"] for row in task_rows if row["goal_id"] is not None}
    if not wanted:
        return
    found = set(
        session.scalars(select(Goal.id).where(Goal.user_id == user_id, Goal.id.in_(wanted)))
    )
    if wanted - found:
        raise GoalNotFound("goal not found")


def _delete_plans(session: Session, plan_ids: list[Any]) -> int:
    if not plan_ids:
        return 0
    session.execute(delete(PlanTask).where(PlanTask.plan_id.in_(plan_ids)))
    session.execute(delete(PlanBlock).where(PlanBlock.plan_id.in_(plan_ids)))
    session.execute(delete(Plan).where(Plan.id.in_(plan_ids)))
    return len(plan_ids)


def save_day_plan(
    session: Session, user_id: Any, plan_date: date, plan: DayPlan, requested: list[TaskSpec]
) -> Any:
    """Store the plan for this user and day, replacing any earlier plan for that day."""
    rows = plan_to_rows(plan, requested)
    _require_own_goals(session, user_id, rows.tasks)
    old_ids = list(
        session.scalars(select(Plan.id).where(Plan.user_id == user_id, Plan.plan_date == plan_date))
    )
    _delete_plans(session, old_ids)

    header = Plan(user_id=user_id, plan_date=plan_date, **rows.plan)
    session.add(header)
    session.flush()
    session.add_all(PlanTask(plan_id=header.id, **row) for row in rows.tasks)
    session.add_all(PlanBlock(plan_id=header.id, **row) for row in rows.blocks)
    session.flush()
    return header.id


def load_day_plan(session: Session, user_id: Any, plan_date: date) -> StoredPlan | None:
    """The stored plan for this user and day, re-validated. None if there is none."""
    header = session.scalar(
        select(Plan).where(Plan.user_id == user_id, Plan.plan_date == plan_date)
    )
    if header is None:
        return None
    tasks = session.scalars(
        select(PlanTask).where(PlanTask.plan_id == header.id).order_by(PlanTask.position)
    ).all()
    blocks = session.scalars(
        select(PlanBlock).where(PlanBlock.plan_id == header.id).order_by(PlanBlock.position)
    ).all()
    rows = StoredRows(
        plan={name: getattr(header, name) for name in PLAN_FIELDS},
        tasks=tuple({name: getattr(row, name) for name in TASK_FIELDS} for row in tasks),
        blocks=tuple({name: getattr(row, name) for name in BLOCK_FIELDS} for row in blocks),
    )
    return rows_to_plan(rows)


def delete_plans_for_user(session: Session, user_id: Any) -> int:
    """Remove every stored plan of one user (used when an account is deleted)."""
    ids = list(session.scalars(select(Plan.id).where(Plan.user_id == user_id)))
    return _delete_plans(session, ids)


def export_plans_for_user(session: Session, user_id: Any) -> list[dict[str, Any]]:
    """Every stored plan of one user as plain, JSON-safe data (used by the data export)."""
    plans = session.scalars(
        select(Plan).where(Plan.user_id == user_id).order_by(Plan.plan_date)
    ).all()
    exported = []
    for plan in plans:
        tasks = session.scalars(
            select(PlanTask).where(PlanTask.plan_id == plan.id).order_by(PlanTask.position)
        ).all()
        blocks = session.scalars(
            select(PlanBlock).where(PlanBlock.plan_id == plan.id).order_by(PlanBlock.position)
        ).all()
        exported.append(
            {
                "date": plan.plan_date.isoformat(),
                "mode": plan.mode,
                "reason": plan.reason,
                "focus_minutes": plan.focus_minutes,
                "tasks": [{name: _plain(getattr(t, name)) for name in TASK_FIELDS} for t in tasks],
                "blocks": [
                    {
                        "kind": b.kind,
                        "title": b.title,
                        "start": format_hhmm(b.start_minute),
                        "end": format_hhmm(b.end_minute),
                        "task_key": b.task_key,
                    }
                    for b in blocks
                ],
            }
        )
    return exported


def delete_day_plan(session: Session, user_id: Any, plan_date: date) -> bool:
    """Remove one user's plan for one day. False if there was none."""
    ids = list(
        session.scalars(select(Plan.id).where(Plan.user_id == user_id, Plan.plan_date == plan_date))
    )
    return _delete_plans(session, ids) > 0
