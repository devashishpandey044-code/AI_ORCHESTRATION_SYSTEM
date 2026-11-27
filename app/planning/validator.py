"""Independent plan checker. It shares no placement logic with the scheduler.

validate_schedule() re-derives every rule from the blocks themselves, so it also
catches a bug in the scheduler, a plan loaded from storage, or a hand-edited plan.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.planning.intervals import find_conflicts
from app.planning.scheduler import Schedule
from app.planning.types import BlockKind, DayContext, Effort, PlanError, TaskSpec


class ViolationCode(StrEnum):
    OVERLAP = "overlap"
    OUTSIDE_AWAKE = "outside_awake"
    FIXED_CHANGED = "fixed_changed"
    FOCUS_OVER_CAPACITY = "focus_over_capacity"
    FOCUS_RUN_TOO_LONG = "focus_run_too_long"
    BACK_TO_BACK_FOCUS = "back_to_back_focus"
    TASK_MINUTES_MISMATCH = "task_minutes_mismatch"
    UNKNOWN_TASK = "unknown_task"
    TASK_ACCOUNTING = "task_accounting"
    FOCUS_MINUTES_WRONG = "focus_minutes_wrong"


@dataclass(frozen=True)
class Violation:
    code: ViolationCode
    message: str


class PlanInvalid(PlanError):
    def __init__(self, violations: list[Violation]):
        self.violations = violations
        super().__init__("; ".join(f"{v.code.value}: {v.message}" for v in violations))


def validate_schedule(
    schedule: Schedule, tasks: list[TaskSpec], context: DayContext
) -> list[Violation]:
    """Return every rule the schedule breaks. An empty list means the plan is valid."""
    found: list[Violation] = []
    specs = {task.key: task for task in tasks}
    blocks = list(schedule.blocks)

    # 1. No overlaps anywhere.
    for first, second in find_conflicts([b.interval for b in blocks]):
        found.append(Violation(ViolationCode.OVERLAP, f"{first} overlaps {second}"))

    # 2. Everything the plan added lies inside the awake window.
    for block in blocks:
        if block.kind in (BlockKind.FIXED, BlockKind.SLEEP):
            continue
        if not context.awake.contains(block.interval):
            found.append(
                Violation(ViolationCode.OUTSIDE_AWAKE, f"'{block.title}' is outside waking hours")
            )

    # 3. Fixed commitments are present exactly as given, and no extra ones appear.
    given = sorted((b.kind.value, b.title, b.interval) for b in context.fixed)
    present = sorted(
        (b.kind.value, b.title, b.interval)
        for b in blocks
        if b.kind in (BlockKind.FIXED, BlockKind.SLEEP)
    )
    if given != present:
        found.append(
            Violation(ViolationCode.FIXED_CHANGED, "fixed commitments were moved, dropped or added")
        )

    # 4. Task blocks: known task, whole minutes, focus limits.
    task_blocks = [b for b in blocks if b.kind is BlockKind.TASK]
    minutes_by_key: dict[str, int] = {}
    focus_blocks = []
    for block in task_blocks:
        spec = specs.get(block.task_key or "")
        if spec is None:
            found.append(Violation(ViolationCode.UNKNOWN_TASK, f"'{block.title}' has no task"))
            continue
        minutes_by_key[spec.key] = minutes_by_key.get(spec.key, 0) + block.interval.length
        if spec.effort is Effort.FOCUS:
            focus_blocks.append(block)
            if block.interval.length > context.max_focus_run:
                found.append(
                    Violation(
                        ViolationCode.FOCUS_RUN_TOO_LONG,
                        f"'{block.title}' runs {block.interval.length} min "
                        f"(limit {context.max_focus_run})",
                    )
                )
    for key, minutes in minutes_by_key.items():
        if minutes != specs[key].minutes:
            found.append(
                Violation(
                    ViolationCode.TASK_MINUTES_MISMATCH,
                    f"task '{key}' has {minutes} min placed, wanted {specs[key].minutes}",
                )
            )

    focus_total = sum(b.interval.length for b in focus_blocks)
    if focus_total > context.focus_capacity:
        found.append(
            Violation(
                ViolationCode.FOCUS_OVER_CAPACITY,
                f"{focus_total} focus min planned, capacity {context.focus_capacity}",
            )
        )
    if schedule.focus_minutes != focus_total:
        found.append(
            Violation(
                ViolationCode.FOCUS_MINUTES_WRONG,
                f"plan says {schedule.focus_minutes} focus min, blocks add up to {focus_total}",
            )
        )

    # 5. Focus pieces must not touch each other when breaks are required.
    if context.break_minutes > 0:
        ordered = sorted(focus_blocks, key=lambda b: b.interval)
        for first, second in zip(ordered, ordered[1:], strict=False):
            if first.interval.end == second.interval.start:
                found.append(
                    Violation(
                        ViolationCode.BACK_TO_BACK_FOCUS,
                        f"no break between '{first.title}' and '{second.title}'",
                    )
                )

    # 6. Every task is either placed or reported, never both and never neither.
    placed_keys = set(minutes_by_key)
    unplaced_keys = [u.task_key for u in schedule.unplaced]
    for key in specs:
        in_placed = key in placed_keys
        in_unplaced = key in unplaced_keys
        if in_placed == in_unplaced:
            state = "both placed and unplaced" if in_placed else "neither placed nor reported"
            found.append(Violation(ViolationCode.TASK_ACCOUNTING, f"task '{key}' is {state}"))
    for key in unplaced_keys:
        if key not in specs:
            found.append(Violation(ViolationCode.UNKNOWN_TASK, f"unplaced '{key}' has no task"))

    return found


def assert_valid(schedule: Schedule, tasks: list[TaskSpec], context: DayContext) -> None:
    violations = validate_schedule(schedule, tasks, context)
    if violations:
        raise PlanInvalid(violations)
