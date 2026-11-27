import random
from dataclasses import replace

import pytest

from app.planning.intervals import Interval
from app.planning.scheduler import Schedule, Unplaced, UnplacedReason, build_schedule
from app.planning.types import (
    BlockKind,
    DayContext,
    Effort,
    PlannedBlock,
    Priority,
    TaskSpec,
)
from app.planning.validator import (
    PlanInvalid,
    ViolationCode,
    assert_valid,
    validate_schedule,
)

AWAKE = Interval(420, 1380)


def task(key, minutes, **kwargs):
    return TaskSpec(key=key, title=f"Task {key}", minutes=minutes, **kwargs)


def lecture(start=540, end=660):
    return PlannedBlock(BlockKind.FIXED, "Lectures", Interval(start, end))


def codes(schedule, tasks, context):
    return {v.code for v in validate_schedule(schedule, tasks, context)}


@pytest.fixture
def day():
    context = DayContext(awake=AWAKE, fixed=(lecture(),), focus_capacity=240)
    tasks = [task("a", 60), task("b", 120), task("c", 30, effort=Effort.LIGHT)]
    return context, tasks, build_schedule(tasks, context)


def with_blocks(schedule, blocks):
    return replace(schedule, blocks=tuple(sorted(blocks, key=lambda b: b.interval)))


def test_scheduler_output_is_valid(day):
    context, tasks, schedule = day
    assert validate_schedule(schedule, tasks, context) == []
    assert_valid(schedule, tasks, context)


def test_overlap_detected(day):
    context, tasks, schedule = day
    extra = PlannedBlock(BlockKind.BREAK, "Break", Interval(550, 570))
    broken = with_blocks(schedule, [*schedule.blocks, extra])
    assert ViolationCode.OVERLAP in codes(broken, tasks, context)


def test_block_outside_waking_hours_detected(day):
    context, tasks, schedule = day
    late = PlannedBlock(BlockKind.BREAK, "Break", Interval(1400, 1420))
    broken = with_blocks(schedule, [*schedule.blocks, late])
    assert ViolationCode.OUTSIDE_AWAKE in codes(broken, tasks, context)


def test_moved_fixed_block_detected(day):
    context, tasks, schedule = day
    blocks = [b for b in schedule.blocks if b.kind is not BlockKind.FIXED]
    blocks.append(PlannedBlock(BlockKind.FIXED, "Lectures", Interval(1000, 1120)))
    assert ViolationCode.FIXED_CHANGED in codes(with_blocks(schedule, blocks), tasks, context)


def test_dropped_fixed_block_detected(day):
    context, tasks, schedule = day
    blocks = [b for b in schedule.blocks if b.kind is not BlockKind.FIXED]
    assert ViolationCode.FIXED_CHANGED in codes(with_blocks(schedule, blocks), tasks, context)


def test_added_fixed_block_detected(day):
    context, tasks, schedule = day
    fake = PlannedBlock(BlockKind.FIXED, "Surprise", Interval(1300, 1330))
    broken = with_blocks(schedule, [*schedule.blocks, fake])
    assert ViolationCode.FIXED_CHANGED in codes(broken, tasks, context)


def test_task_with_wrong_total_minutes_detected(day):
    context, tasks, schedule = day
    blocks = []
    for b in schedule.blocks:
        if b.kind is BlockKind.TASK and b.task_key == "c":
            b = replace(b, interval=Interval(b.interval.start, b.interval.end - 10))
        blocks.append(b)
    assert ViolationCode.TASK_MINUTES_MISMATCH in codes(
        with_blocks(schedule, blocks), tasks, context
    )


def test_unknown_task_block_detected(day):
    context, tasks, schedule = day
    ghost = PlannedBlock(BlockKind.TASK, "Ghost", Interval(1200, 1230), task_key="zzz")
    broken = with_blocks(schedule, [*schedule.blocks, ghost])
    assert ViolationCode.UNKNOWN_TASK in codes(broken, tasks, context)


def test_focus_run_too_long_detected():
    context = DayContext(awake=AWAKE, max_focus_run=60)
    spec = task("a", 120)
    block = PlannedBlock(BlockKind.TASK, "Task a", Interval(420, 540), task_key="a")
    plan = Schedule(blocks=(block,), unplaced=(), focus_minutes=120)
    assert ViolationCode.FOCUS_RUN_TOO_LONG in codes(plan, [spec], context)


def test_focus_over_capacity_detected():
    context = DayContext(awake=AWAKE, focus_capacity=60)
    spec = task("a", 90)
    block = PlannedBlock(BlockKind.TASK, "Task a", Interval(420, 510), task_key="a")
    plan = Schedule(blocks=(block,), unplaced=(), focus_minutes=90)
    assert ViolationCode.FOCUS_OVER_CAPACITY in codes(plan, [spec], context)


def test_back_to_back_focus_detected():
    context = DayContext(awake=AWAKE, break_minutes=10)
    specs = [task("a", 60), task("b", 60)]
    blocks = (
        PlannedBlock(BlockKind.TASK, "Task a", Interval(420, 480), task_key="a"),
        PlannedBlock(BlockKind.TASK, "Task b", Interval(480, 540), task_key="b"),
    )
    plan = Schedule(blocks=blocks, unplaced=(), focus_minutes=120)
    assert ViolationCode.BACK_TO_BACK_FOCUS in codes(plan, specs, context)


def test_back_to_back_allowed_when_no_breaks_required():
    context = DayContext(awake=AWAKE, break_minutes=0)
    specs = [task("a", 60), task("b", 60)]
    blocks = (
        PlannedBlock(BlockKind.TASK, "Task a", Interval(420, 480), task_key="a"),
        PlannedBlock(BlockKind.TASK, "Task b", Interval(480, 540), task_key="b"),
    )
    plan = Schedule(blocks=blocks, unplaced=(), focus_minutes=120)
    assert validate_schedule(plan, specs, context) == []


def test_wrong_reported_focus_minutes_detected(day):
    context, tasks, schedule = day
    broken = replace(schedule, focus_minutes=schedule.focus_minutes + 5)
    assert ViolationCode.FOCUS_MINUTES_WRONG in codes(broken, tasks, context)


def test_task_missing_from_plan_and_report_detected(day):
    context, tasks, schedule = day
    blocks = [b for b in schedule.blocks if b.task_key != "c"]
    assert ViolationCode.TASK_ACCOUNTING in codes(with_blocks(schedule, blocks), tasks, context)


def test_task_both_placed_and_unplaced_detected(day):
    context, tasks, schedule = day
    both = replace(
        schedule, unplaced=(Unplaced("a", UnplacedReason.NO_SPACE, "x"),)
    )
    assert ViolationCode.TASK_ACCOUNTING in codes(both, tasks, context)


def test_unplaced_unknown_task_detected(day):
    context, tasks, schedule = day
    odd = replace(schedule, unplaced=(Unplaced("nope", UnplacedReason.NO_SPACE, "x"),))
    assert ViolationCode.UNKNOWN_TASK in codes(odd, tasks, context)


def test_assert_valid_raises_with_all_violations(day):
    context, tasks, schedule = day
    broken = replace(schedule, focus_minutes=1)
    with pytest.raises(PlanInvalid) as caught:
        assert_valid(broken, tasks, context)
    assert caught.value.violations
    assert "focus_minutes_wrong" in str(caught.value)


def test_scheduler_never_produces_an_invalid_plan():
    """The validator is the scheduler's referee: 500 random days must all pass it."""
    rng = random.Random(23)
    for _ in range(500):
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
            focus_capacity=rng.choice([60, 120, 240, 360]),
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
        schedule = build_schedule(tasks, context)
        assert validate_schedule(schedule, tasks, context) == []
