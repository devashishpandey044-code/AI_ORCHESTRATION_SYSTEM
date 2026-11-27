import dataclasses
import json
import random
from dataclasses import replace

import pytest

from app.planning.fallback import PlanMode, plan_day
from app.planning.intervals import Interval
from app.planning.records import (
    BLOCK_FIELDS,
    PLAN_FIELDS,
    TASK_FIELDS,
    StoredPlanCorrupt,
    StoredRows,
    plan_to_rows,
    rows_to_plan,
)
from app.planning.scheduler import Schedule
from app.planning.types import (
    BlockKind,
    DayContext,
    Effort,
    PlanError,
    PlannedBlock,
    Priority,
    TaskSpec,
)
from app.planning.validator import PlanInvalid

AWAKE = Interval(420, 1380)
LECTURES = PlannedBlock(BlockKind.FIXED, "Lectures", Interval(540, 780))


def task(key, minutes, **kwargs):
    return TaskSpec(key=key, title=f"Task {key}", minutes=minutes, **kwargs)


def _by_task(item):
    return item.task_key


def same_plan(a, b):
    assert a.mode == b.mode
    assert a.reason == b.reason
    assert a.schedule == b.schedule
    assert a.context == b.context
    assert sorted(a.tasks, key=lambda t: t.key) == sorted(b.tasks, key=lambda t: t.key)
    assert sorted(a.dropped, key=_by_task) == sorted(b.dropped, key=_by_task)
    assert sorted(a.trimmed, key=_by_task) == sorted(b.trimmed, key=_by_task)


def with_rows(rows, **changes):
    return dataclasses.replace(rows, **changes)


@pytest.fixture
def full():
    tasks = [task("a", 120, priority=Priority.MUST, goal_id=7), task("b", 45), task("c", 30)]
    context = DayContext(awake=AWAKE, fixed=(LECTURES,), focus_capacity=240)
    plan = plan_day(tasks, context)
    return tasks, plan


@pytest.fixture
def minimum():
    tasks = [
        task("a", 120, priority=Priority.MUST),
        task("b", 90),
        task("c", 60, priority=Priority.COULD),
    ]
    plan = plan_day(tasks, DayContext(awake=AWAKE, fixed=(LECTURES,)), low_energy=True)
    return tasks, plan


def test_field_lists_match_the_rows(full):
    tasks, plan = full
    rows = plan_to_rows(plan, tasks)
    assert tuple(rows.plan) == PLAN_FIELDS
    assert all(tuple(row) == TASK_FIELDS for row in rows.tasks)
    assert all(tuple(row) == BLOCK_FIELDS for row in rows.blocks)


def test_rows_contain_only_plain_values(full):
    tasks, plan = full
    rows = plan_to_rows(plan, tasks)
    json.dumps([rows.plan, list(rows.tasks), list(rows.blocks)])


def test_full_plan_round_trip(full):
    tasks, plan = full
    stored = rows_to_plan(plan_to_rows(plan, tasks))
    same_plan(stored.day_plan, plan)
    assert list(stored.requested) == tasks


def test_minimum_plan_round_trip_keeps_dropped_trimmed_and_original_minutes(minimum):
    tasks, plan = minimum
    assert plan.mode is PlanMode.MINIMUM and plan.dropped and plan.trimmed
    stored = rows_to_plan(plan_to_rows(plan, tasks))
    same_plan(stored.day_plan, plan)
    assert [t.minutes for t in stored.requested] == [120, 90, 60]


def test_unplaced_task_keeps_its_reason(full):
    tasks = [task("a", 60), task("b", 60, priority=Priority.COULD)]
    plan = plan_day(tasks, DayContext(awake=AWAKE, focus_capacity=60))
    rows = plan_to_rows(plan, tasks)
    unplaced_rows = [r for r in rows.tasks if r["status"] == "unplaced"]
    assert [r["key"] for r in unplaced_rows] == ["b"]
    assert unplaced_rows[0]["reason"] == "over_focus_capacity"
    same_plan(rows_to_plan(rows).day_plan, plan)


def test_row_order_does_not_matter(full):
    tasks, plan = full
    rows = plan_to_rows(plan, tasks)
    shuffled = with_rows(
        rows, tasks=tuple(reversed(rows.tasks)), blocks=tuple(reversed(rows.blocks))
    )
    same_plan(rows_to_plan(shuffled).day_plan, plan)


def test_plan_to_rows_rejects_duplicate_requested_keys(full):
    tasks, plan = full
    with pytest.raises(PlanError):
        plan_to_rows(plan, [*tasks, tasks[0]])


def test_plan_to_rows_rejects_a_plan_that_mentions_unrequested_tasks(full):
    tasks, plan = full
    with pytest.raises(PlanError):
        plan_to_rows(plan, tasks[:-1])


def test_plan_to_rows_rejects_requested_task_that_is_neither_planned_nor_dropped(full):
    tasks, plan = full
    with pytest.raises(PlanError):
        plan_to_rows(plan, [*tasks, task("extra", 30)])


def test_plan_to_rows_rejects_planned_task_with_no_block_and_no_report(full):
    tasks, plan = full
    blocks = tuple(b for b in plan.schedule.blocks if b.task_key != "c")
    broken = replace(plan, schedule=replace(plan.schedule, blocks=blocks))
    with pytest.raises(PlanError):
        plan_to_rows(broken, tasks)


def test_overlapping_stored_blocks_are_rejected(full):
    tasks, plan = full
    rows = plan_to_rows(plan, tasks)
    damaged = [dict(b) for b in rows.blocks]
    task_block = next(b for b in damaged if b["kind"] == "task")
    task_block["start_minute"], task_block["end_minute"] = 560, 620  # inside the lecture
    with pytest.raises(PlanInvalid):
        rows_to_plan(with_rows(rows, blocks=tuple(damaged)))


def test_wrong_stored_focus_minutes_are_rejected(full):
    tasks, plan = full
    rows = plan_to_rows(plan, tasks)
    with pytest.raises(PlanInvalid):
        rows_to_plan(with_rows(rows, plan={**rows.plan, "focus_minutes": 999}))


@pytest.mark.parametrize(
    "table,column,value",
    [
        ("tasks", "priority", 9),
        ("tasks", "effort", "heroic"),
        ("tasks", "status", "vanished"),
        ("tasks", "minutes", 5),
        ("tasks", "reason", "nonsense"),
        ("blocks", "kind", "party"),
        ("blocks", "start_minute", 2000),
        ("blocks", "end_minute", 0),
        ("plan", "mode", "chaos"),
        ("plan", "awake_end", 100),
        ("plan", "break_minutes", -1),
    ],
)
def test_damaged_values_raise_corrupt_or_invalid(table, column, value):
    tasks2 = [task("a", 60), task("b", 60, priority=Priority.COULD)]
    plan = plan_day(tasks2, DayContext(awake=AWAKE, focus_capacity=60))
    rows = plan_to_rows(plan, tasks2)
    if table == "plan":
        damaged = with_rows(rows, plan={**rows.plan, column: value})
    elif table == "tasks":
        index = next(i for i, r in enumerate(rows.tasks) if r["status"] == "unplaced")
        edited = [dict(r) for r in rows.tasks]
        edited[index][column] = value
        damaged = with_rows(rows, tasks=tuple(edited))
    else:
        edited = [dict(r) for r in rows.blocks]
        edited[0][column] = value
        damaged = with_rows(rows, blocks=tuple(edited))
    with pytest.raises((StoredPlanCorrupt, PlanInvalid)):
        rows_to_plan(damaged)


def test_missing_field_is_corrupt(full):
    tasks, plan = full
    rows = plan_to_rows(plan, tasks)
    without = {k: v for k, v in rows.plan.items() if k != "focus_capacity"}
    with pytest.raises(StoredPlanCorrupt):
        rows_to_plan(with_rows(rows, plan=without))


def test_stored_rows_type_is_exported():
    assert StoredRows.__name__ == "StoredRows"


def test_random_days_survive_storage():
    rng = random.Random(41)
    for _ in range(300):
        fixed, cursor = [], 420
        for _ in range(rng.randrange(0, 4)):
            start = cursor + rng.randrange(0, 120)
            end = start + rng.randrange(30, 120)
            if end > 1380:
                break
            fixed.append(PlannedBlock(BlockKind.FIXED, "Class", Interval(start, end)))
            cursor = end
        context = DayContext(
            awake=AWAKE,
            fixed=tuple(fixed),
            focus_capacity=rng.choice([0, 60, 120, 240, 360]),
            max_focus_run=rng.choice([30, 60, 90]),
            break_minutes=rng.choice([0, 5, 10, 15]),
        )
        tasks = [
            task(
                f"t{i}",
                rng.randrange(10, 241),
                priority=rng.choice(list(Priority)),
                effort=rng.choice(list(Effort)),
            )
            for i in range(rng.randrange(0, 9))
        ]
        plan = plan_day(tasks, context, low_energy=rng.random() < 0.3)
        rows = plan_to_rows(plan, tasks)
        json.dumps([rows.plan, list(rows.tasks), list(rows.blocks)])
        stored = rows_to_plan(rows)
        same_plan(stored.day_plan, plan)
        assert list(stored.requested) == tasks
        assert isinstance(stored.day_plan.schedule, Schedule)
