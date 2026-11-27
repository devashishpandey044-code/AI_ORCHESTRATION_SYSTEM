"""Deterministic daily scheduler: places tasks into the free time around fixed blocks.

Rules, in order of importance:
  1. Fixed commitments and sleep never move, and nothing overlaps them.
  2. Everything is placed inside the awake window.
  3. Total FOCUS minutes never exceed the day's focus capacity.
  4. FOCUS work is cut into pieces no longer than max_focus_run, each followed by a break.
  5. Tasks are tried in order: priority, then longer first, then key. Same input, same plan.
A task is placed whole or not at all. What cannot be placed is reported with a reason.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.planning.intervals import Interval, subtract
from app.planning.types import (
    MAX_TASK_MINUTES,
    BlockKind,
    DayContext,
    Effort,
    PlanError,
    PlannedBlock,
    TaskSpec,
)

_TITLE_LIMIT = 120


class UnplacedReason(StrEnum):
    OVER_FOCUS_CAPACITY = "over_focus_capacity"
    NO_SPACE = "no_space"


@dataclass(frozen=True)
class Unplaced:
    task_key: str
    reason: UnplacedReason
    message: str


@dataclass(frozen=True)
class Schedule:
    blocks: tuple[PlannedBlock, ...]
    unplaced: tuple[Unplaced, ...]
    focus_minutes: int


def _split_minutes(task: TaskSpec, context: DayContext) -> list[int]:
    """Focus work longer than max_focus_run is cut into near-equal pieces."""
    if task.effort is not Effort.FOCUS or task.minutes <= context.max_focus_run:
        return [task.minutes]
    pieces = -(-task.minutes // context.max_focus_run)  # ceiling division
    base, extra = divmod(task.minutes, pieces)
    return [base + (1 if i < extra else 0) for i in range(pieces)]


def _piece_title(title: str, index: int, total: int) -> str:
    if total == 1:
        return title
    suffix = f" ({index + 1}/{total})"
    return title[: _TITLE_LIMIT - len(suffix)] + suffix


def _place_task(
    task: TaskSpec, context: DayContext, placed: list[PlannedBlock]
) -> list[PlannedBlock] | None:
    """Return `placed` plus this task's blocks, or None if any piece does not fit."""
    working = list(placed)
    is_focus = task.effort is Effort.FOCUS
    pieces = _split_minutes(task, context)
    for index, length in enumerate(pieces):
        busy = context.busy + [block.interval for block in working]
        gaps = subtract(context.awake, busy)
        needed = length + (context.break_minutes if is_focus else 0)
        chosen = None
        for gap in gaps:
            if gap.length >= needed or (gap.length >= length and gap.end == context.awake.end):
                chosen = gap
                break
        if chosen is None:
            return None
        start = chosen.start
        working.append(
            PlannedBlock(
                BlockKind.TASK,
                _piece_title(task.title, index, len(pieces)),
                Interval(start, start + length),
                task_key=task.key,
            )
        )
        break_end = start + length + context.break_minutes
        if is_focus and context.break_minutes > 0 and break_end <= chosen.end:
            working.append(
                PlannedBlock(BlockKind.BREAK, "Break", Interval(start + length, break_end))
            )
    return working


def build_schedule(tasks: list[TaskSpec], context: DayContext) -> Schedule:
    keys = [task.key for task in tasks]
    if len(set(keys)) != len(keys):
        raise PlanError("task keys must be unique")
    for task in tasks:
        if task.minutes > MAX_TASK_MINUTES:  # defensive: TaskSpec already enforces this
            raise PlanError("task too long")

    ordered = sorted(tasks, key=lambda t: (t.priority.value, -t.minutes, t.key))
    placed: list[PlannedBlock] = []
    unplaced: list[Unplaced] = []
    focus_used = 0

    for task in ordered:
        if task.effort is Effort.FOCUS and focus_used + task.minutes > context.focus_capacity:
            unplaced.append(
                Unplaced(
                    task.key,
                    UnplacedReason.OVER_FOCUS_CAPACITY,
                    f"Would pass today's focus limit of {context.focus_capacity} minutes.",
                )
            )
            continue
        result = _place_task(task, context, placed)
        if result is None:
            unplaced.append(
                Unplaced(task.key, UnplacedReason.NO_SPACE, "No free time long enough today.")
            )
            continue
        placed = result
        if task.effort is Effort.FOCUS:
            focus_used += task.minutes

    blocks = sorted([*context.fixed, *placed], key=lambda b: b.interval)
    return Schedule(tuple(blocks), tuple(unplaced), focus_used)
