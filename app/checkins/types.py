"""Check-in types: what the user reports after a day.

A check-in says, per planned task, how it went. Everything is validated on
construction so bad data cannot reach the comparison or the database.
"""

from dataclasses import dataclass
from enum import StrEnum

MAX_NOTE_CHARS = 500
MAX_ACTUAL_MINUTES = 1440


class CheckinError(ValueError):
    """Raised when a check-in is malformed."""


class TaskStatus(StrEnum):
    DONE = "done"
    PARTIAL = "partial"
    SKIPPED = "skipped"


class BlockReason(StrEnum):
    TOO_TIRED = "too_tired"
    INTERRUPTED = "interrupted"
    UNDERESTIMATED = "underestimated"
    LOST_MOTIVATION = "lost_motivation"
    UNPLANNED_EVENT = "unplanned_event"
    OTHER = "other"


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class TaskOutcome:
    key: str
    status: TaskStatus
    actual_minutes: int
    reason: BlockReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key.strip():
            raise CheckinError("task key must be a non-empty string")
        if not isinstance(self.status, TaskStatus):
            raise CheckinError("status must be a TaskStatus")
        if not _is_int(self.actual_minutes):
            raise CheckinError("actual_minutes must be an integer")
        if not 0 <= self.actual_minutes <= MAX_ACTUAL_MINUTES:
            raise CheckinError(f"actual_minutes must be 0..{MAX_ACTUAL_MINUTES}")
        if self.reason is not None and not isinstance(self.reason, BlockReason):
            raise CheckinError("reason must be a BlockReason or None")
        if self.status is TaskStatus.SKIPPED:
            if self.actual_minutes != 0:
                raise CheckinError("a skipped task has 0 actual minutes")
            if self.reason is None:
                raise CheckinError("a skipped task needs a reason")
        else:
            if self.actual_minutes == 0:
                raise CheckinError(f"a {self.status.value} task needs actual minutes above 0")
        if self.status is TaskStatus.DONE and self.reason is not None:
            raise CheckinError("a done task has no block reason")


@dataclass(frozen=True)
class Checkin:
    outcomes: tuple[TaskOutcome, ...]
    energy: int | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.outcomes, tuple):
            raise CheckinError("outcomes must be a tuple")
        keys = []
        for outcome in self.outcomes:
            if not isinstance(outcome, TaskOutcome):
                raise CheckinError("outcomes must contain TaskOutcome values")
            keys.append(outcome.key)
        if len(set(keys)) != len(keys):
            raise CheckinError("each task can be reported only once")
        if self.energy is not None:
            if not _is_int(self.energy) or not 1 <= self.energy <= 5:
                raise CheckinError("energy must be an integer 1..5 or None")
        if not isinstance(self.note, str) or len(self.note) > MAX_NOTE_CHARS:
            raise CheckinError(f"note must be text up to {MAX_NOTE_CHARS} characters")
