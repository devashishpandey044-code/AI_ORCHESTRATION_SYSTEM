"""Find repeating roadblocks in several days of check-in reports. Pure code.

A roadblock is a reason that keeps costing planned minutes: it must happen at
least `min_occurrences` times on at least `min_days` different days. One bad
day is noise, not a pattern.
"""

from dataclasses import dataclass

from app.checkins.compare import DayReport, percent
from app.checkins.types import BlockReason, CheckinError, TaskStatus

DEFAULT_MIN_OCCURRENCES = 3
DEFAULT_MIN_DAYS = 2


@dataclass(frozen=True)
class Roadblock:
    reason: BlockReason
    occurrences: int
    days_affected: int
    minutes_lost: int
    share_percent: int  # of all minutes lost to reported reasons


@dataclass(frozen=True)
class PatternReport:
    days: int
    roadblocks: tuple[Roadblock, ...]
    # actual / planned for finished tasks, in percent (130 means 30% over); None if no data
    estimate_ratio_percent: int | None
    unreported_percent: int | None  # of planned tasks never reported; None if nothing planned


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CheckinError(f"{name} must be an integer of at least 1")
    return value


def analyze(
    reports: list[DayReport] | tuple[DayReport, ...],
    min_occurrences: int = DEFAULT_MIN_OCCURRENCES,
    min_days: int = DEFAULT_MIN_DAYS,
) -> PatternReport:
    min_occurrences = _positive_int("min_occurrences", min_occurrences)
    min_days = _positive_int("min_days", min_days)
    if not isinstance(reports, (list, tuple)) or not all(
        isinstance(r, DayReport) for r in reports
    ):
        raise CheckinError("reports must be a list of DayReport values")

    occurrences: dict[BlockReason, int] = {}
    days_with: dict[BlockReason, set[int]] = {}
    lost: dict[BlockReason, int] = {}
    done_planned = done_actual = 0
    planned_tasks = unreported_tasks = 0

    for day_index, report in enumerate(reports):
        planned_tasks += len(report.results) + len(report.unreported)
        unreported_tasks += len(report.unreported)
        for result in report.results:
            if result.status is TaskStatus.DONE:
                done_planned += result.planned_minutes
                done_actual += result.actual_minutes
            if result.reason is None:
                continue
            missed = result.planned_minutes - result.counted_minutes
            occurrences[result.reason] = occurrences.get(result.reason, 0) + 1
            days_with.setdefault(result.reason, set()).add(day_index)
            lost[result.reason] = lost.get(result.reason, 0) + missed

    total_lost = sum(lost.values())
    found = []
    for reason, count in occurrences.items():
        days = len(days_with[reason])
        if count < min_occurrences or days < min_days:
            continue
        share = percent(lost[reason], total_lost) if total_lost else 0
        found.append(Roadblock(reason, count, days, lost[reason], share))
    found.sort(key=lambda r: (-r.minutes_lost, -r.occurrences, r.reason.value))

    ratio = percent(done_actual, done_planned) if done_planned else None
    unreported = percent(unreported_tasks, planned_tasks) if planned_tasks else None
    return PatternReport(len(reports), tuple(found), ratio, unreported)
