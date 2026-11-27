"""Minimum viable day: a smaller, honest plan for days the full plan cannot work.

The full plan is tried first. The minimum viable day is used when the user asks for a low-energy
day, or when the full plan cannot fit a MUST task. It keeps only the most important tasks, shrinks
each to a short first step, and halves the focus limit. Nothing is hidden: every dropped or shrunk
task is listed with a reason, and the final plan is always re-checked by the validator.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from app.planning.scheduler import Schedule, build_schedule
from app.planning.types import MIN_TASK_MINUTES, DayContext, Effort, PlanError, Priority, TaskSpec
from app.planning.validator import assert_valid

MVD_MAX_TASKS = 2
MVD_TASK_MINUTES = 30
MVD_MIN_FOCUS = 30


class PlanMode(StrEnum):
    FULL = "full"
    MINIMUM = "minimum"


class DropReason(StrEnum):
    NOT_ESSENTIAL_TODAY = "not_essential_today"
    OVER_REDUCED_CAPACITY = "over_reduced_capacity"


@dataclass(frozen=True)
class Dropped:
    task_key: str
    reason: DropReason


@dataclass(frozen=True)
class Trimmed:
    task_key: str
    from_minutes: int
    to_minutes: int


@dataclass(frozen=True)
class DayPlan:
    mode: PlanMode
    schedule: Schedule
    tasks: tuple[TaskSpec, ...]  # the tasks `schedule` was built and validated against
    context: DayContext  # the context it was built and validated against
    dropped: tuple[Dropped, ...] = ()
    trimmed: tuple[Trimmed, ...] = ()
    reason: str = ""


def minimum_viable_day(
    tasks: list[TaskSpec],
    context: DayContext,
    *,
    max_tasks: int = MVD_MAX_TASKS,
    task_minutes: int = MVD_TASK_MINUTES,
    reason: str = "",
) -> DayPlan:
    if isinstance(max_tasks, bool) or not isinstance(max_tasks, int) or max_tasks < 1:
        raise PlanError("max_tasks must be a whole number, 1 or more")
    if isinstance(task_minutes, bool) or not isinstance(task_minutes, int):
        raise PlanError("task_minutes must be a whole number")
    if task_minutes < MIN_TASK_MINUTES:
        raise PlanError(f"task_minutes must be at least {MIN_TASK_MINUTES}")
    keys = [task.key for task in tasks]
    if len(set(keys)) != len(keys):
        raise PlanError("task keys must be unique")

    reduced_capacity = min(context.focus_capacity, max(MVD_MIN_FOCUS, context.focus_capacity // 2))
    reduced_context = replace(context, focus_capacity=reduced_capacity)

    shrunk: list[tuple[TaskSpec, int]] = []  # (task after trimming, original minutes)
    for task in tasks:
        new_minutes = min(task.minutes, task_minutes)
        shrunk.append((replace(task, minutes=new_minutes), task.minutes))
    shrunk.sort(key=lambda pair: (pair[0].priority.value, pair[0].minutes, pair[0].key))

    kept: list[TaskSpec] = []
    dropped: list[Dropped] = []
    trimmed: list[Trimmed] = []
    focus_used = 0
    for task, original in shrunk:
        if len(kept) >= max_tasks:
            dropped.append(Dropped(task.key, DropReason.NOT_ESSENTIAL_TODAY))
            continue
        if task.effort is Effort.FOCUS and focus_used + task.minutes > reduced_capacity:
            dropped.append(Dropped(task.key, DropReason.OVER_REDUCED_CAPACITY))
            continue
        kept.append(task)
        if task.effort is Effort.FOCUS:
            focus_used += task.minutes
        if task.minutes != original:
            trimmed.append(Trimmed(task.key, original, task.minutes))

    schedule = build_schedule(kept, reduced_context)
    assert_valid(schedule, kept, reduced_context)
    return DayPlan(
        mode=PlanMode.MINIMUM,
        schedule=schedule,
        tasks=tuple(kept),
        context=reduced_context,
        dropped=tuple(dropped),
        trimmed=tuple(trimmed),
        reason=reason or "Minimum viable day.",
    )


def plan_day(
    tasks: list[TaskSpec], context: DayContext, *, low_energy: bool = False
) -> DayPlan:
    """Plan one day: full plan if it works, otherwise the minimum viable day."""
    if low_energy:
        return minimum_viable_day(tasks, context, reason="You asked for a lighter day.")

    schedule = build_schedule(tasks, context)
    assert_valid(schedule, tasks, context)
    must_keys = {task.key for task in tasks if task.priority is Priority.MUST}
    missed_must = [u.task_key for u in schedule.unplaced if u.task_key in must_keys]
    if missed_must:
        return minimum_viable_day(
            tasks,
            context,
            reason="The full plan could not fit every must-do task, so here is a smaller one.",
        )
    return DayPlan(
        mode=PlanMode.FULL,
        schedule=schedule,
        tasks=tuple(tasks),
        context=context,
        reason="Full plan.",
    )
