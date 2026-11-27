"""Stored check-ins. One per stored plan, so one per user per day.

Every query is scoped to one user. A check-in is validated against that day's placed
tasks before it is stored. The functions flush but do not commit: the caller commits.
"""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.checkins.compare import DayReport, compare_day
from app.checkins.records import CheckinRows, OutcomeRow, checkin_to_rows, rows_to_checkin
from app.checkins.types import Checkin, CheckinError
from app.db.checkin_models import CheckinOutcomeRow, CheckinRow
from app.db.plan_models import Plan, PlanTask


class PlanNotFoundForCheckin(CheckinError):
    """There is no stored plan for this user and day, so there is nothing to check in on."""


def _plan(session: Session, user_id: Any, plan_date: date) -> Plan | None:
    return session.scalar(
        select(Plan).where(Plan.user_id == user_id, Plan.plan_date == plan_date)
    )


def _placed_minutes(session: Session, plan_id: Any) -> dict[str, int]:
    rows = session.execute(
        select(PlanTask.key, PlanTask.planned_minutes).where(
            PlanTask.plan_id == plan_id, PlanTask.status == "placed"
        )
    )
    return {key: minutes for key, minutes in rows if minutes and minutes > 0}


def _delete_rows(session: Session, checkin_ids: list[Any]) -> None:
    if not checkin_ids:
        return
    session.execute(delete(CheckinOutcomeRow).where(CheckinOutcomeRow.checkin_id.in_(checkin_ids)))
    session.execute(delete(CheckinRow).where(CheckinRow.id.in_(checkin_ids)))


def _find(session: Session, user_id: Any, plan_date: date) -> tuple[Plan, CheckinRow] | None:
    plan = _plan(session, user_id, plan_date)
    if plan is None:
        return None
    row = session.scalar(
        select(CheckinRow).where(CheckinRow.plan_id == plan.id, CheckinRow.user_id == user_id)
    )
    return (plan, row) if row is not None else None


def save_checkin(session: Session, user_id: Any, plan_date: date, checkin: Checkin) -> None:
    """Store the check-in for this day, replacing an earlier one. Nothing is stored if invalid."""
    plan = _plan(session, user_id, plan_date)
    if plan is None:
        raise PlanNotFoundForCheckin(f"no stored plan for {plan_date.isoformat()}")
    compare_day(_placed_minutes(session, plan.id), checkin)  # rejects tasks that were not planned
    existing = list(
        session.scalars(
            select(CheckinRow.id).where(
                CheckinRow.plan_id == plan.id, CheckinRow.user_id == user_id
            )
        )
    )
    _delete_rows(session, existing)

    rows = checkin_to_rows(checkin)
    header = CheckinRow(
        id=uuid.uuid4(), user_id=user_id, plan_id=plan.id, energy=rows.energy, note=rows.note
    )
    session.add(header)
    session.flush()
    for row in rows.outcomes:
        session.add(
            CheckinOutcomeRow(
                id=uuid.uuid4(),
                checkin_id=header.id,
                task_key=row.task_key,
                status=row.status,
                actual_minutes=row.actual_minutes,
                reason=row.reason,
            )
        )
    session.flush()


def load_checkin(session: Session, user_id: Any, plan_date: date) -> Checkin | None:
    """The stored check-in for this user and day, re-validated. None if there is none."""
    found = _find(session, user_id, plan_date)
    if found is None:
        return None
    _, header = found
    outcomes = session.scalars(
        select(CheckinOutcomeRow).where(CheckinOutcomeRow.checkin_id == header.id)
    ).all()
    rows = CheckinRows(
        energy=header.energy,
        note=header.note,
        outcomes=tuple(
            OutcomeRow(o.task_key, o.status, o.actual_minutes, o.reason) for o in outcomes
        ),
    )
    return rows_to_checkin(rows)


def load_day_report(session: Session, user_id: Any, plan_date: date) -> DayReport | None:
    """Plan versus actual for one day. None if the day has no check-in."""
    found = _find(session, user_id, plan_date)
    if found is None:
        return None
    plan, _ = found
    checkin = load_checkin(session, user_id, plan_date)
    if checkin is None:
        return None
    return compare_day(_placed_minutes(session, plan.id), checkin)


def delete_checkin(session: Session, user_id: Any, plan_date: date) -> bool:
    found = _find(session, user_id, plan_date)
    if found is None:
        return False
    _delete_rows(session, [found[1].id])
    return True


def delete_checkins_for_user(session: Session, user_id: Any) -> int:
    """Remove every stored check-in of one user (used when an account is deleted)."""
    ids = list(session.scalars(select(CheckinRow.id).where(CheckinRow.user_id == user_id)))
    _delete_rows(session, ids)
    return len(ids)


def export_checkins_for_user(session: Session, user_id: Any) -> list[dict[str, Any]]:
    """Every stored check-in of one user as plain, JSON-safe data (used by the data export)."""
    found = session.execute(
        select(CheckinRow, Plan.plan_date)
        .join(Plan, Plan.id == CheckinRow.plan_id)
        .where(CheckinRow.user_id == user_id)
        .order_by(Plan.plan_date)
    ).all()
    exported = []
    for header, plan_date in found:
        outcomes = session.scalars(
            select(CheckinOutcomeRow)
            .where(CheckinOutcomeRow.checkin_id == header.id)
            .order_by(CheckinOutcomeRow.task_key)
        ).all()
        exported.append(
            {
                "date": plan_date.isoformat(),
                "energy": header.energy,
                "note": header.note,
                "outcomes": [
                    {
                        "task_key": o.task_key,
                        "status": o.status,
                        "actual_minutes": o.actual_minutes,
                        "reason": o.reason,
                    }
                    for o in outcomes
                ],
            }
        )
    return exported


def load_reports(session: Session, user_id: Any, start: date, end: date) -> list[DayReport]:
    """Plan-versus-actual reports for every day from start to end (inclusive) that has a
    check-in, oldest first."""
    days = list(
        session.scalars(
            select(Plan.plan_date)
            .join(CheckinRow, CheckinRow.plan_id == Plan.id)
            .where(
                Plan.user_id == user_id,
                CheckinRow.user_id == user_id,
                Plan.plan_date >= start,
                Plan.plan_date <= end,
            )
            .order_by(Plan.plan_date)
        )
    )
    reports = []
    for day in days:
        report = load_day_report(session, user_id, day)
        if report is not None:
            reports.append(report)
    return reports
