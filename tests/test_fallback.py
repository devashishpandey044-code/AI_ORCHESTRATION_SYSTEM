import random

import pytest

from app.planning.fallback import (
    DropReason,
    PlanMode,
    minimum_viable_day,
    plan_day,
)
from app.planning.intervals import Interval
from app.planning.scheduler import build_schedule
from app.planning.types import (
    BlockKind,
    DayContext,
    Effort,
    PlanError,
    PlannedBlock,
    Priority,
    TaskSpec,
)
from app.planning.validator import validate_schedule

AWAKE = Interval(420, 1380)


def task(key, minutes, **kwargs):
    return TaskSpec(key=key, title=f"Task {key}", minutes=minutes, **kwargs)


def test_full_plan_used_when_everything_fits():
    tasks = [task("a", 60), task("b", 45)]
    context = DayContext(awake=AWAKE)
    plan = plan_day(tasks, context)
    assert plan.mode is PlanMode.FULL
    assert plan.schedule == build_schedule(tasks, context)
    assert plan.dropped == () and plan.trimmed == ()
    assert plan.tasks == tuple(tasks)


def test_low_energy_forces_minimum_day():
    tasks = [task("a", 120, priority=Priority.MUST), task("b", 90), task("c", 60)]
    plan = plan_day(tasks, DayContext(awake=AWAKE, focus_capacity=240), low_energy=True)
    assert plan.mode is PlanMode.MINIMUM
    assert len(plan.tasks) <= 2
    assert plan.context.focus_capacity == 120
    assert "lighter" in plan.reason


def test_minimum_day_keeps_the_most_important_and_shrinks_them():
    tasks = [
        task("could", 60, priority=Priority.COULD),
        task("must", 120, priority=Priority.MUST),
        task("should", 45, priority=Priority.SHOULD),
    ]
    plan = minimum_viable_day(tasks, DayContext(awake=AWAKE, focus_capacity=240))
    assert [t.key for t in plan.tasks] == ["must", "should"]
    assert all(t.minutes <= 30 for t in plan.tasks)
    assert {(t.task_key, t.from_minutes, t.to_minutes) for t in plan.trimmed} == {
        ("must", 120, 30),
        ("should", 45, 30),
    }
    assert [(d.task_key, d.reason) for d in plan.dropped] == [
        ("could", DropReason.NOT_ESSENTIAL_TODAY)
    ]


def test_short_tasks_are_not_changed():
    plan = minimum_viable_day([task("a", 20)], DayContext(awake=AWAKE))
    assert plan.trimmed == ()
    assert plan.tasks[0].minutes == 20


def test_every_input_task_is_kept_or_dropped():
    tasks = [task(f"t{i}", 40) for i in range(5)]
    plan = minimum_viable_day(tasks, DayContext(awake=AWAKE))
    kept = {t.key for t in plan.tasks}
    dropped = {d.task_key for d in plan.dropped}
    assert kept | dropped == {t.key for t in tasks}
    assert kept.isdisjoint(dropped)


def test_zero_focus_capacity_keeps_only_light_work():
    tasks = [task("f", 30), task("l", 30, effort=Effort.LIGHT)]
    plan = minimum_viable_day(tasks, DayContext(awake=AWAKE, focus_capacity=0))
    assert [t.key for t in plan.tasks] == ["l"]
    assert plan.dropped[0].reason is DropReason.OVER_REDUCED_CAPACITY


def test_must_task_that_does_not_fit_triggers_fallback():
    tight = DayContext(awake=Interval(420, 540), focus_capacity=120)
    tasks = [task(f"m{i}", 60, priority=Priority.MUST) for i in range(3)]
    plan = plan_day(tasks, tight)
    assert plan.mode is PlanMode.MINIMUM
    assert "smaller" in plan.reason


def test_unplaced_could_task_does_not_trigger_fallback():
    context = DayContext(awake=AWAKE, focus_capacity=60)
    tasks = [task("a", 60, priority=Priority.MUST), task("b", 60, priority=Priority.COULD)]
    plan = plan_day(tasks, context)
    assert plan.mode is PlanMode.FULL
    assert [u.task_key for u in plan.schedule.unplaced] == ["b"]


def test_fixed_commitments_survive_the_fallback():
    lecture = PlannedBlock(BlockKind.FIXED, "Lectures", Interval(540, 660))
    context = DayContext(awake=AWAKE, fixed=(lecture,))
    plan = plan_day([task("a", 90)], context, low_energy=True)
    assert lecture in plan.schedule.blocks


def test_inputs_are_not_modified():
    tasks = [task("a", 120)]
    context = DayContext(awake=AWAKE, focus_capacity=240)
    plan_day(tasks, context, low_energy=True)
    assert tasks[0].minutes == 120
    assert context.focus_capacity == 240


def test_plan_is_valid_against_the_tasks_and_context_it_carries():
    tasks = [task("a", 120, priority=Priority.MUST), task("b", 50)]
    plan = plan_day(tasks, DayContext(awake=AWAKE), low_energy=True)
    assert validate_schedule(plan.schedule, list(plan.tasks), plan.context) == []


@pytest.mark.parametrize("bad", [0, -1, 1.5, True, None])
def test_max_tasks_validated(bad):
    with pytest.raises(PlanError):
        minimum_viable_day([task("a", 30)], DayContext(awake=AWAKE), max_tasks=bad)


@pytest.mark.parametrize("bad", [9, 0, 30.5, True])
def test_task_minutes_validated(bad):
    with pytest.raises(PlanError):
        minimum_viable_day([task("a", 30)], DayContext(awake=AWAKE), task_minutes=bad)


def test_duplicate_keys_rejected():
    with pytest.raises(PlanError):
        minimum_viable_day([task("a", 30), task("a", 40)], DayContext(awake=AWAKE))


def test_empty_task_list_gives_an_empty_plan():
    plan = plan_day([], DayContext(awake=AWAKE), low_energy=True)
    assert plan.mode is PlanMode.MINIMUM
    assert plan.schedule.blocks == ()


def test_random_days_always_produce_a_valid_plan():
    rng = random.Random(31)
    for _ in range(400):
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
        assert validate_schedule(plan.schedule, list(plan.tasks), plan.context) == []
        if plan.mode is PlanMode.MINIMUM:
            assert len(plan.tasks) <= 2
            assert plan.context.focus_capacity <= context.focus_capacity
            accounted = {t.key for t in plan.tasks} | {d.task_key for d in plan.dropped}
            assert accounted == {t.key for t in tasks}
