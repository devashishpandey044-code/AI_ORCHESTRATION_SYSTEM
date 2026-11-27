"""Compare a plan with a check-in. Pure code, whole minutes, no model call."""

from dataclasses import dataclass

from app.checkins.types import BlockReason, Checkin, CheckinError, TaskStatus


@dataclass(frozen=True)
class TaskResult:
    key: str
    planned_minutes: int
    actual_minutes: int
    status: TaskStatus
    reason: BlockReason | None

    @property
    def overrun_minutes(self) -> int:
        return max(0, self.actual_minutes - self.planned_minutes)

    @property
    def counted_minutes(self) -> int:
        """Minutes that count toward the plan (never more than planned)."""
        return min(self.actual_minutes, self.planned_minutes)


@dataclass(frozen=True)
class DayReport:
    results: tuple[TaskResult, ...]
    unreported: tuple[str, ...]
    planned_minutes: int
    counted_minutes: int
    overrun_minutes: int
    adherence_percent: int | None  # None when nothing was planned


def percent(part: int, whole: int) -> int:
    """Whole-number percent, rounded half up, using integers only."""
    return (100 * part + whole // 2) // whole


def compare_day(planned: dict[str, int], checkin: Checkin) -> DayReport:
    """planned maps task key to planned minutes for the tasks that were placed."""
    for key, minutes in planned.items():
        if not isinstance(key, str) or isinstance(minutes, bool) or not isinstance(minutes, int):
            raise CheckinError("planned must map text keys to integer minutes")
        if minutes <= 0:
            raise CheckinError(f"planned minutes for {key!r} must be above 0")
    unknown = sorted(o.key for o in checkin.outcomes if o.key not in planned)
    if unknown:
        raise CheckinError(f"check-in reports tasks that were not planned: {unknown}")

    reported = {o.key: o for o in checkin.outcomes}
    results = []
    for key in sorted(reported):
        o = reported[key]
        results.append(TaskResult(key, planned[key], o.actual_minutes, o.status, o.reason))
    unreported = tuple(sorted(k for k in planned if k not in reported))

    planned_total = sum(planned.values())
    counted = sum(r.counted_minutes for r in results)
    overrun = sum(r.overrun_minutes for r in results)
    adherence = percent(counted, planned_total) if planned_total else None
    return DayReport(tuple(results), unreported, planned_total, counted, overrun, adherence)
