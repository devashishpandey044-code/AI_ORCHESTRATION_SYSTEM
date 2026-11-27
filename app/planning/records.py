"""Plan <-> stored rows, as plain dicts. No database code lives here.

plan_to_rows() flattens a DayPlan into three lists of dicts (plan header, tasks, blocks).
rows_to_plan() rebuilds the plan from those dicts and re-checks it with the validator, so a
plan that was edited or damaged in storage is rejected instead of shown to the user.
The database layer only copies these dicts in and out of tables.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.planning.fallback import DayPlan, Dropped, DropReason, PlanMode, Trimmed
from app.planning.intervals import Interval, IntervalError
from app.planning.scheduler import Schedule, Unplaced, UnplacedReason
from app.planning.types import (
    BlockKind,
    DayContext,
    Effort,
    PlanError,
    PlannedBlock,
    Priority,
    TaskSpec,
)
from app.planning.validator import PlanInvalid, assert_valid

PLAN_FIELDS = (
    "mode",
    "reason",
    "awake_start",
    "awake_end",
    "focus_capacity",
    "max_focus_run",
    "break_minutes",
    "focus_minutes",
)
TASK_FIELDS = (
    "position",
    "key",
    "title",
    "minutes",
    "planned_minutes",
    "priority",
    "effort",
    "goal_id",
    "status",
    "reason",
    "note",
)
BLOCK_FIELDS = ("position", "kind", "title", "start_minute", "end_minute", "task_key")

STATUS_PLACED = "placed"
STATUS_UNPLACED = "unplaced"
STATUS_DROPPED = "dropped"


class StoredPlanCorrupt(PlanError):
    """Stored rows cannot be turned back into a plan."""


@dataclass(frozen=True)
class StoredRows:
    plan: dict[str, Any]
    tasks: tuple[dict[str, Any], ...]
    blocks: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class StoredPlan:
    day_plan: DayPlan
    requested: tuple[TaskSpec, ...]  # what the user asked for, before any shrinking


def plan_to_rows(plan: DayPlan, requested: list[TaskSpec]) -> StoredRows:
    keys = [task.key for task in requested]
    if len(set(keys)) != len(keys):
        raise PlanError("requested task keys must be unique")
    requested_by_key = {task.key: task for task in requested}
    kept = {task.key: task for task in plan.tasks}
    dropped = {item.task_key: item for item in plan.dropped}
    unplaced = {item.task_key: item for item in plan.schedule.unplaced}
    placed_keys = {
        block.task_key for block in plan.schedule.blocks if block.kind is BlockKind.TASK
    }

    for key in [*kept, *dropped]:
        if key not in requested_by_key:
            raise PlanError(f"plan mentions task '{key}' that was not requested")
    if set(kept) & set(dropped):
        raise PlanError("a task cannot be both planned and dropped")
    for key in requested_by_key:
        if key not in kept and key not in dropped:
            raise PlanError(f"requested task '{key}' is neither planned nor dropped")

    task_rows = []
    for position, task in enumerate(requested):
        row = {
            "position": position,
            "key": task.key,
            "title": task.title,
            "minutes": task.minutes,
            "planned_minutes": None,
            "priority": task.priority.value,
            "effort": task.effort.value,
            "goal_id": task.goal_id,
            "status": STATUS_DROPPED,
            "reason": None,
            "note": None,
        }
        if task.key in kept:
            row["planned_minutes"] = kept[task.key].minutes
            if task.key in placed_keys:
                row["status"] = STATUS_PLACED
            elif task.key in unplaced:
                row["status"] = STATUS_UNPLACED
                row["reason"] = unplaced[task.key].reason.value
                row["note"] = unplaced[task.key].message
            else:
                raise PlanError(f"planned task '{task.key}' is neither placed nor unplaced")
        else:
            row["reason"] = dropped[task.key].reason.value
        task_rows.append(row)

    block_rows = [
        {
            "position": position,
            "kind": block.kind.value,
            "title": block.title,
            "start_minute": block.interval.start,
            "end_minute": block.interval.end,
            "task_key": block.task_key,
        }
        for position, block in enumerate(plan.schedule.blocks)
    ]
    header = {
        "mode": plan.mode.value,
        "reason": plan.reason,
        "awake_start": plan.context.awake.start,
        "awake_end": plan.context.awake.end,
        "focus_capacity": plan.context.focus_capacity,
        "max_focus_run": plan.context.max_focus_run,
        "break_minutes": plan.context.break_minutes,
        "focus_minutes": plan.schedule.focus_minutes,
    }
    return StoredRows(header, tuple(task_rows), tuple(block_rows))


def _need(row: dict[str, Any], fields: tuple[str, ...], what: str) -> None:
    missing = [name for name in fields if name not in row]
    if missing:
        raise StoredPlanCorrupt(f"stored {what} is missing {missing}")


def rows_to_plan(rows: StoredRows) -> StoredPlan:
    """Rebuild the plan and re-validate it. Raises StoredPlanCorrupt or PlanInvalid."""
    try:
        return _rebuild(rows)
    except (PlanInvalid, StoredPlanCorrupt):
        raise
    except (ValueError, TypeError, KeyError, IntervalError) as error:
        raise StoredPlanCorrupt(f"stored plan is damaged: {error}") from error


def _rebuild(rows: StoredRows) -> StoredPlan:
    header = rows.plan
    _need(header, PLAN_FIELDS, "plan")

    task_rows = sorted(rows.tasks, key=lambda row: row["position"])
    block_rows = sorted(rows.blocks, key=lambda row: row["position"])

    requested: list[TaskSpec] = []
    kept: list[TaskSpec] = []
    dropped: list[Dropped] = []
    trimmed: list[Trimmed] = []
    unplaced: list[Unplaced] = []
    for row in task_rows:
        _need(row, TASK_FIELDS, "task")
        base = TaskSpec(
            key=row["key"],
            title=row["title"],
            minutes=row["minutes"],
            priority=Priority(row["priority"]),
            effort=Effort(row["effort"]),
            goal_id=row["goal_id"],
        )
        requested.append(base)
        status = row["status"]
        if status == STATUS_DROPPED:
            dropped.append(Dropped(base.key, DropReason(row["reason"])))
            continue
        if status not in (STATUS_PLACED, STATUS_UNPLACED):
            raise StoredPlanCorrupt(f"unknown task status '{status}'")
        planned = row["planned_minutes"]
        task = base if planned is None else TaskSpec(
            key=base.key,
            title=base.title,
            minutes=planned,
            priority=base.priority,
            effort=base.effort,
            goal_id=base.goal_id,
        )
        kept.append(task)
        if task.minutes != base.minutes:
            trimmed.append(Trimmed(base.key, base.minutes, task.minutes))
        if status == STATUS_UNPLACED:
            unplaced.append(
                Unplaced(base.key, UnplacedReason(row["reason"]), row["note"] or "")
            )

    # The scheduler reports unplaced tasks in the order it tried them; restore that order.
    tried = {t.key: (t.priority.value, -t.minutes, t.key) for t in kept}
    unplaced.sort(key=lambda item: tried[item.task_key])

    blocks = []
    for row in block_rows:
        _need(row, BLOCK_FIELDS, "block")
        blocks.append(
            PlannedBlock(
                BlockKind(row["kind"]),
                row["title"],
                Interval(row["start_minute"], row["end_minute"]),
                task_key=row["task_key"],
            )
        )

    fixed = tuple(b for b in blocks if b.kind in (BlockKind.FIXED, BlockKind.SLEEP))
    context = DayContext(
        awake=Interval(header["awake_start"], header["awake_end"]),
        fixed=fixed,
        focus_capacity=header["focus_capacity"],
        max_focus_run=header["max_focus_run"],
        break_minutes=header["break_minutes"],
    )
    schedule = Schedule(tuple(blocks), tuple(unplaced), header["focus_minutes"])
    assert_valid(schedule, kept, context)
    day_plan = DayPlan(
        mode=PlanMode(header["mode"]),
        schedule=schedule,
        tasks=tuple(kept),
        context=context,
        dropped=tuple(dropped),
        trimmed=tuple(trimmed),
        reason=header["reason"],
    )
    return StoredPlan(day_plan=day_plan, requested=tuple(requested))
