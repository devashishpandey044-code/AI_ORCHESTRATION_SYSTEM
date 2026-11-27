import dataclasses

import pytest

from app.planning.intervals import Interval
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


def test_task_spec_defaults_and_title_cleanup():
    task = TaskSpec(key="t1", title="  Read   chapter 3 ", minutes=45)
    assert task.title == "Read chapter 3"
    assert task.priority is Priority.SHOULD
    assert task.effort is Effort.FOCUS
    assert task.goal_id is None


@pytest.mark.parametrize("minutes", [9, 241, 0, -5, 30.5, True, "30", None])
def test_task_minutes_validated(minutes):
    with pytest.raises(PlanError):
        TaskSpec(key="t", title="x", minutes=minutes)


@pytest.mark.parametrize("title", ["", "   ", None, 5, "x" * 121])
def test_task_title_validated(title):
    with pytest.raises(PlanError):
        TaskSpec(key="t", title=title, minutes=30)


@pytest.mark.parametrize("key", ["", "  ", None])
def test_task_key_validated(key):
    with pytest.raises(PlanError):
        TaskSpec(key=key, title="x", minutes=30)


def test_task_priority_and_effort_must_be_enums():
    with pytest.raises(PlanError):
        TaskSpec(key="t", title="x", minutes=30, priority=1)
    with pytest.raises(PlanError):
        TaskSpec(key="t", title="x", minutes=30, effort="focus")


def test_task_boundaries_accepted():
    assert TaskSpec(key="a", title="x", minutes=10).minutes == 10
    assert TaskSpec(key="b", title="x", minutes=240).minutes == 240


def test_task_spec_is_immutable():
    task = TaskSpec(key="t", title="x", minutes=30)
    with pytest.raises(dataclasses.FrozenInstanceError):
        task.minutes = 60


def test_task_block_needs_key_and_others_must_not_have_one():
    interval = Interval(600, 660)
    assert PlannedBlock(BlockKind.TASK, "Study", interval, task_key="t1").task_key == "t1"
    with pytest.raises(PlanError):
        PlannedBlock(BlockKind.TASK, "Study", interval)
    with pytest.raises(PlanError):
        PlannedBlock(BlockKind.BREAK, "Rest", interval, task_key="t1")


def test_block_type_checks():
    with pytest.raises(PlanError):
        PlannedBlock("task", "x", Interval(0, 10), task_key="t")
    with pytest.raises(PlanError):
        PlannedBlock(BlockKind.FIXED, "x", (0, 10))
    with pytest.raises(PlanError):
        PlannedBlock(BlockKind.FIXED, " ", Interval(0, 10))


def test_day_context_defaults():
    ctx = DayContext(awake=AWAKE)
    assert ctx.busy == []
    assert ctx.focus_capacity == 240


def test_day_context_busy_lists_fixed_intervals():
    cls = PlannedBlock(BlockKind.FIXED, "Class", Interval(540, 600))
    ctx = DayContext(awake=AWAKE, fixed=(cls,))
    assert ctx.busy == [Interval(540, 600)]


def test_fixed_commitments_may_not_overlap():
    a = PlannedBlock(BlockKind.FIXED, "Class", Interval(540, 600))
    b = PlannedBlock(BlockKind.FIXED, "Lab", Interval(590, 650))
    with pytest.raises(PlanError):
        DayContext(awake=AWAKE, fixed=(a, b))


def test_touching_fixed_commitments_are_fine():
    a = PlannedBlock(BlockKind.FIXED, "Class", Interval(540, 600))
    b = PlannedBlock(BlockKind.FIXED, "Lab", Interval(600, 660))
    assert len(DayContext(awake=AWAKE, fixed=(a, b)).fixed) == 2


def test_only_fixed_and_sleep_allowed_as_fixed():
    task = PlannedBlock(BlockKind.TASK, "Study", Interval(540, 600), task_key="t")
    with pytest.raises(PlanError):
        DayContext(awake=AWAKE, fixed=(task,))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"focus_capacity": -1},
        {"focus_capacity": 961},
        {"max_focus_run": 5},
        {"break_minutes": -3},
        {"focus_capacity": 1.5},
        {"break_minutes": True},
    ],
)
def test_day_context_numbers_validated(kwargs):
    with pytest.raises(PlanError):
        DayContext(awake=AWAKE, **kwargs)


def test_awake_must_be_interval():
    with pytest.raises(PlanError):
        DayContext(awake=(420, 1380))
