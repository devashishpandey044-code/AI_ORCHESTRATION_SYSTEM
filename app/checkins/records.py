"""Convert a check-in to plain rows and back. Pure code, no database.

Rows hold only text, ints and None, so the database layer stays thin. Loading
re-validates everything, so a damaged row cannot become a believable check-in.
"""

from dataclasses import dataclass

from app.checkins.types import BlockReason, Checkin, CheckinError, TaskOutcome, TaskStatus


class StoredCheckinCorrupt(CheckinError):
    """Raised when stored rows do not describe a valid check-in."""


@dataclass(frozen=True)
class OutcomeRow:
    task_key: str
    status: str
    actual_minutes: int
    reason: str | None


@dataclass(frozen=True)
class CheckinRows:
    energy: int | None
    note: str
    outcomes: tuple[OutcomeRow, ...]


def checkin_to_rows(checkin: Checkin) -> CheckinRows:
    rows = tuple(
        OutcomeRow(
            task_key=o.key,
            status=o.status.value,
            actual_minutes=o.actual_minutes,
            reason=o.reason.value if o.reason is not None else None,
        )
        for o in sorted(checkin.outcomes, key=lambda o: o.key)
    )
    return CheckinRows(checkin.energy, checkin.note, rows)


def rows_to_checkin(rows: CheckinRows) -> Checkin:
    try:
        outcomes = []
        for row in sorted(rows.outcomes, key=lambda r: str(r.task_key)):
            reason = BlockReason(row.reason) if row.reason is not None else None
            outcomes.append(
                TaskOutcome(row.task_key, TaskStatus(row.status), row.actual_minutes, reason)
            )
        return Checkin(tuple(outcomes), rows.energy, rows.note)
    except (CheckinError, ValueError, TypeError, AttributeError) as exc:
        raise StoredCheckinCorrupt(f"stored check-in is invalid: {exc}") from exc
