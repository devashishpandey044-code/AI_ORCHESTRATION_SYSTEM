import random

import pytest

from app.planning.intervals import Interval, find_conflicts
from app.planning.scheduler import UnplacedReason, build_schedule
from app.planning.types import (
    BlockKind,
    DayContext,
    Effort,
    PlanError,
    PlannedBlock,
    Priority,
    TaskSpec,
)

AWAKE = Interval(420, 1380)  # 07:00 to 23:00


def ctx(**kwargs):
    return DayContext(awake=kwargs.pop("awake", AWAKE), **kwargs)


def task(key, minutes, **kwargs):
    return TaskSpec(key=key, title=f"Task {key}", minutes=minutes, **kwargs)


def class_block(start, end, title="Class"):
    return PlannedBlock(BlockKind.FIXED, title, Interval(start, end))


def task_blocks(schedule):
    return [b for b in schedule.blocks if b.kind is BlockKind.TASK]


def test_empty_day_places_nothing():
    schedule = build_schedule([], ctx())
    assert schedule.blocks == ()
    assert schedule.unplaced == ()
    assert schedule.focus_minutes == 0


def test_single_task_goes_to_earliest_time_with_a_break():
    schedule = build_schedule([task("a", 60)], ctx())
    kinds = [(b.kind, b.interval) for b in schedule.blocks]
    assert kinds == [
        (BlockKind.TASK, Interval(420, 480)),
        (BlockKind.BREAK, Interval(480, 490)),
    ]
    assert schedule.focus_minutes == 60


def test_light_tasks_get_no_break_and_do_not_use_focus_capacity():
    schedule = build_schedule([task("a", 30, effort=Effort.LIGHT)], ctx(focus_capacity=0))
    assert [b.kind for b in schedule.blocks] == [BlockKind.TASK]
    assert schedule.focus_minutes == 0
    assert schedule.unplaced == ()


def test_tasks_avoid_fixed_commitments():
    schedule = build_schedule([task("a", 60)], ctx(fixed=(class_block(420, 600),)))
    assert task_blocks(schedule)[0].interval == Interval(600, 660)


def test_task_fits_in_a_gap_between_commitments():
    fixed = (class_block(420, 500), class_block(580, 700, "Lab"))
    schedule = build_schedule([task("a", 60)], ctx(fixed=fixed))
    assert task_blocks(schedule)[0].interval == Interval(500, 560)


def test_priority_decides_who_gets_scarce_time():
    tight = ctx(awake=Interval(420, 540), focus_capacity=120)
    tasks = [task("low", 60, priority=Priority.COULD), task("high", 60, priority=Priority.MUST)]
    schedule = build_schedule(tasks, tight)
    assert [b.task_key for b in task_blocks(schedule)] == ["high"]
    assert [u.task_key for u in schedule.unplaced] == ["low"]
    assert schedule.unplaced[0].reason is UnplacedReason.NO_SPACE


def test_focus_capacity_is_respected():
    tasks = [task("a", 60), task("b", 60), task("c", 60)]
    schedule = build_schedule(tasks, ctx(focus_capacity=120))
    assert schedule.focus_minutes == 120
    assert len(schedule.unplaced) == 1
    assert schedule.unplaced[0].reason is UnplacedReason.OVER_FOCUS_CAPACITY


def test_long_focus_task_is_split_with_breaks():
    schedule = build_schedule([task("a", 150)], ctx(max_focus_run=90, focus_capacity=240))
    pieces = task_blocks(schedule)
    assert [p.interval.length for p in pieces] == [75, 75]
    assert [p.title for p in pieces] == ["Task a (1/2)", "Task a (2/2)"]
    assert sum(p.interval.length for p in pieces) == 150
    assert schedule.blocks[1].kind is BlockKind.BREAK


def test_long_light_task_is_not_split():
    schedule = build_schedule([task("a", 200, effort=Effort.LIGHT)], ctx())
    assert [p.interval.length for p in task_blocks(schedule)] == [200]


def test_task_is_all_or_nothing_when_a_piece_does_not_fit():
    tight = ctx(awake=Interval(420, 540), focus_capacity=120, max_focus_run=60)
    schedule = build_schedule([task("a", 120)], tight)
    assert task_blocks(schedule) == []
    assert [u.task_key for u in schedule.unplaced] == ["a"]
    assert schedule.focus_minutes == 0


def test_last_piece_may_end_exactly_at_the_end_of_the_day():
    tight = ctx(awake=Interval(420, 480), focus_capacity=60)
    schedule = build_schedule([task("a", 60)], tight)
    assert task_blocks(schedule)[0].interval == Interval(420, 480)
    assert all(b.kind is not BlockKind.BREAK for b in schedule.blocks)


def test_zero_break_minutes_adds_no_break_blocks():
    schedule = build_schedule([task("a", 30), task("b", 30)], ctx(break_minutes=0))
    assert all(b.kind is not BlockKind.BREAK for b in schedule.blocks)
    assert [b.interval for b in task_blocks(schedule)] == [Interval(420, 450), Interval(450, 480)]


def test_duplicate_keys_rejected():
    with pytest.raises(PlanError):
        build_schedule([task("a", 30), task("a", 40)], ctx())


def test_same_input_gives_same_plan():
    tasks = [task("a", 45), task("b", 90, priority=Priority.MUST), task("c", 30)]
    context = ctx(fixed=(class_block(540, 660),))
    assert build_schedule(tasks, context) == build_schedule(list(reversed(tasks)), context)


def test_fixed_blocks_are_kept_and_output_is_sorted():
    fixed = (class_block(900, 960), class_block(540, 600))
    schedule = build_schedule([task("a", 30)], ctx(fixed=fixed))
    starts = [b.interval.start for b in schedule.blocks]
    assert starts == sorted(starts)
    assert sum(1 for b in schedule.blocks if b.kind is BlockKind.FIXED) == 2


def test_long_titles_stay_valid_when_split():
    long_title = "x" * 120
    spec = TaskSpec(key="a", title=long_title, minutes=150)
    schedule = build_schedule([spec], ctx(max_focus_run=90))
    assert all(len(b.title) <= 120 for b in task_blocks(schedule))


def test_random_days_always_satisfy_the_hard_rules():
    rng = random.Random(11)
    for _ in range(300):
        fixed = []
        cursor = 420
        for _ in range(rng.randrange(0, 4)):
            start = cursor + rng.randrange(0, 120)
            end = start + rng.randrange(30, 120)
            if end > 1380:
                break
            fixed.append(class_block(start, end))
            cursor = end
        context = ctx(
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

        intervals = [b.interval for b in schedule.blocks]
        assert find_conflicts(intervals) == []
        fixed_spans = [f.interval for f in context.fixed]
        assert all(context.awake.contains(i) or i in fixed_spans for i in intervals)
        assert schedule.focus_minutes <= context.focus_capacity
        placed = {b.task_key for b in task_blocks(schedule)}
        unplaced = {u.task_key for u in schedule.unplaced}
        assert placed.isdisjoint(unplaced)
        assert placed | unplaced == {t.key for t in tasks}
        for spec in tasks:
            if spec.key in placed:
                pieces = [b for b in task_blocks(schedule) if b.task_key == spec.key]
                assert sum(b.interval.length for b in pieces) == spec.minutes
        for block in task_blocks(schedule):
            spec = next(t for t in tasks if t.key == block.task_key)
            if spec.effort is Effort.FOCUS:
                assert block.interval.length <= max(context.max_focus_run, 1)
