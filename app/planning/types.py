"""The scheduler's vocabulary: tasks to place, blocks placed, and the day's context.

These are plain validated objects with no database or model involved. The
scheduler (Day 3) consumes TaskSpec and DayContext and produces PlannedBlock
lists; the validator (Day 4) checks those lists against the same rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.planning.intervals import Interval


class PlanError(ValueError):
    """Raised when a task, block or day context breaks a basic rule."""


class BlockKind(str, Enum):
    FIXED = "fixed"  # classes, work: given by the user, never moved
    SLEEP = "sleep"
    TASK = "task"  # work the scheduler placed
    BREAK = "break"
    INTERVENTION = "intervention"  # a library method placed as a block


class Priority(int, Enum):
    MUST = 1
    SHOULD = 2
    COULD = 3


class Effort(str, Enum):
    LIGHT = "light"
    FOCUS = "focus"  # deep work: counts against the daily focus capacity


MIN_TASK_MINUTES = 10
MAX_TASK_MINUTES = 240


def _clean_title(title: str) -> str:
    if not isinstance(title, str) or not title.strip():
        raise PlanError("title must be non-empty text")
    cleaned = " ".join(title.split())
    if len(cleaned) > 120:
        raise PlanError("title must be at most 120 characters")
    return cleaned


@dataclass(frozen=True)
class TaskSpec:
    """Something the user wants done today, before it has a time."""

    key: str
    title: str
    minutes: int
    priority: Priority = Priority.SHOULD
    effort: Effort = Effort.FOCUS
    goal_id: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key.strip():
            raise PlanError("task key must be non-empty text")
        object.__setattr__(self, "title", _clean_title(self.title))
        if isinstance(self.minutes, bool) or not isinstance(self.minutes, int):
            raise PlanError("task minutes must be a whole number")
        if not MIN_TASK_MINUTES <= self.minutes <= MAX_TASK_MINUTES:
            raise PlanError(
                f"task minutes must be {MIN_TASK_MINUTES}-{MAX_TASK_MINUTES}, got {self.minutes}"
            )
        if not isinstance(self.priority, Priority):
            raise PlanError("priority must be a Priority")
        if not isinstance(self.effort, Effort):
            raise PlanError("effort must be an Effort")


@dataclass(frozen=True)
class PlannedBlock:
    """A time range with a meaning. `task_key` links task blocks back to a TaskSpec."""

    kind: BlockKind
    title: str
    interval: Interval
    task_key: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, BlockKind):
            raise PlanError("kind must be a BlockKind")
        object.__setattr__(self, "title", _clean_title(self.title))
        if not isinstance(self.interval, Interval):
            raise PlanError("interval must be an Interval")
        if self.kind is BlockKind.TASK and not self.task_key:
            raise PlanError("a task block needs a task_key")
        if self.kind is not BlockKind.TASK and self.task_key is not None:
            raise PlanError("only task blocks carry a task_key")


@dataclass(frozen=True)
class DayContext:
    """What is fixed about the day.

    awake: the waking window the scheduler may use. fixed: commitments that never move.
    focus_capacity: most minutes of FOCUS work the user can sustain in one day.
    break_minutes: gap kept after any focus block longer than max_focus_run.
    """

    awake: Interval
    fixed: tuple[PlannedBlock, ...] = ()
    focus_capacity: int = 240
    max_focus_run: int = 90
    break_minutes: int = 10
    notes: list[str] = field(default_factory=list, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.awake, Interval):
            raise PlanError("awake must be an Interval")
        for name in ("focus_capacity", "max_focus_run", "break_minutes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise PlanError(f"{name} must be a whole number of minutes, 0 or more")
        if self.max_focus_run < MIN_TASK_MINUTES:
            raise PlanError(f"max_focus_run must be at least {MIN_TASK_MINUTES} minutes")
        if self.focus_capacity > self.awake.length:
            raise PlanError("focus_capacity cannot exceed the awake window")
        seen: list[Interval] = []
        for block in self.fixed:
            if block.kind not in (BlockKind.FIXED, BlockKind.SLEEP):
                raise PlanError("only fixed and sleep blocks can be given as fixed")
            for other in seen:
                if block.interval.overlaps(other):
                    raise PlanError(f"fixed commitments overlap: {block.title}")
            seen.append(block.interval)

    @property
    def busy(self) -> list[Interval]:
        return [block.interval for block in self.fixed]
