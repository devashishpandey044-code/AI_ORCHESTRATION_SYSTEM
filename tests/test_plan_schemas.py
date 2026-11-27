import json
import uuid
from datetime import date

import pytest
from pydantic import ValidationError

from app.planning.fallback import PlanMode, plan_day
from app.planning.schemas import MAX_FIXED, MAX_TASKS, PlanRequest, to_domain, to_response
from app.planning.types import BlockKind, Effort, Priority
from app.planning.validator import validate_schedule

DAY = date(2026, 11, 28)


def request(**changes):
    base = {
        "tasks": [
            {"key": "dsa", "title": "DSA practice", "minutes": 120, "priority": 1},
            {"key": "proj", "title": "Project work", "minutes": 45},
            {"key": "read", "title": "Read a paper", "minutes": 30, "priority": 3},
        ],
        "fixed": [{"title": "Lectures", "start": "09:00", "end": "13:00"}],
    }
    base.update(changes)
    return PlanRequest.model_validate(base)


def test_defaults_are_filled_in():
    req = PlanRequest.model_validate({})
    assert req.tasks == [] and req.low_energy is False
    assert (req.awake_start, req.awake_end) == ("07:00", "23:00")
    assert (req.focus_capacity, req.max_focus_run, req.break_minutes) == (240, 90, 10)


def test_request_converts_to_planner_objects():
    tasks, context, low_energy = to_domain(request(low_energy=True))
    assert low_energy is True
    assert [t.key for t in tasks] == ["dsa", "proj", "read"]
    assert tasks[0].priority is Priority.MUST
    assert tasks[1].effort is Effort.FOCUS
    assert context.awake.start == 420 and context.awake.end == 1380
    assert context.fixed[0].kind is BlockKind.FIXED
    assert (context.fixed[0].interval.start, context.fixed[0].interval.end) == (540, 780)


def test_sleep_blocks_are_accepted():
    req = request(fixed=[{"title": "Nap", "start": "14:00", "end": "14:30", "kind": "sleep"}])
    _, context, _ = to_domain(req)
    assert context.fixed[0].kind is BlockKind.SLEEP


def test_goal_id_accepts_integers_and_uuids():
    a = request(tasks=[{"key": "a", "title": "x", "minutes": 30, "goal_id": 5}])
    b = request(tasks=[{"key": "a", "title": "x", "minutes": 30, "goal_id": str(uuid.uuid4())}])
    assert to_domain(a)[0][0].goal_id == 5
    assert isinstance(to_domain(b)[0][0].goal_id, uuid.UUID)


@pytest.mark.parametrize(
    "changes",
    [
        {"tasks": [{"key": "a", "title": "x", "minutes": 30}] * 2},  # duplicate keys
        {"tasks": [{"key": "a b", "title": "x", "minutes": 30}]},  # space in key
        {"tasks": [{"key": "", "title": "x", "minutes": 30}]},
        {"tasks": [{"key": "a", "title": "", "minutes": 30}]},
        {"tasks": [{"key": "a", "title": "x" * 121, "minutes": 30}]},
        {"tasks": [{"key": "a", "title": "x", "minutes": 9}]},
        {"tasks": [{"key": "a", "title": "x", "minutes": 241}]},
        {"tasks": [{"key": "a", "title": "x", "minutes": 30, "priority": 0}]},
        {"tasks": [{"key": "a", "title": "x", "minutes": 30, "priority": 4}]},
        {"tasks": [{"key": "a", "title": "x", "minutes": 30, "effort": "heroic"}]},
        {"tasks": [{"key": "a", "title": "x", "minutes": 30, "surprise": 1}]},
        {"tasks": [{"key": f"t{i}", "title": "x", "minutes": 30} for i in range(MAX_TASKS + 1)]},
        {"awake_start": "7:00"},
        {"awake_end": "25:00"},
        {"awake_start": "23:00", "awake_end": "07:00"},
        {"fixed": [{"title": "x", "start": "10:00", "end": "09:00"}]},
        {"fixed": [{"title": "x", "start": "10:00", "end": "10:00"}]},
        {"fixed": [{"title": "x", "start": "ab:cd", "end": "11:00"}]},
        {"fixed": [{"title": "x", "start": "10:00", "end": "11:00", "kind": "task"}]},
        {
            "fixed": [
                {"title": "a", "start": "09:00", "end": "11:00"},
                {"title": "b", "start": "10:00", "end": "12:00"},
            ]
        },
        {"fixed": [{"title": "x", "start": "09:00", "end": "10:00"}] * (MAX_FIXED + 1)},
        {"focus_capacity": -1},
        {"focus_capacity": 961},
        {"focus_capacity": 900, "awake_start": "09:00", "awake_end": "12:00"},
        {"max_focus_run": 5},
        {"break_minutes": 61},
        {"low_energy": "maybe"},
        {"unknown_option": True},
    ],
)
def test_bad_requests_are_rejected(changes):
    with pytest.raises(ValidationError):
        request(**changes)


def test_touching_fixed_blocks_are_fine():
    req = request(
        fixed=[
            {"title": "a", "start": "09:00", "end": "10:00"},
            {"title": "b", "start": "10:00", "end": "11:00"},
        ]
    )
    assert len(to_domain(req)[1].fixed) == 2


def test_end_of_day_time_is_accepted():
    req = request(awake_end="24:00")
    assert to_domain(req)[1].awake.end == 1440


def test_response_shape_and_times():
    tasks, context, low = to_domain(request())
    plan = plan_day(tasks, context, low_energy=low)
    out = to_response(DAY, plan)
    assert out.mode == "full" and out.date == DAY
    assert out.blocks[0].start == "07:00"
    assert any(b.kind == "fixed" and (b.start, b.end) == ("09:00", "13:00") for b in out.blocks)
    json.dumps(out.model_dump(mode="json"))
    assert validate_schedule(plan.schedule, list(plan.tasks), plan.context) == []


def test_low_energy_response_lists_dropped_and_trimmed():
    tasks, context, low = to_domain(request(low_energy=True))
    plan = plan_day(tasks, context, low_energy=low)
    out = to_response(DAY, plan)
    assert plan.mode is PlanMode.MINIMUM
    assert out.mode == "minimum"
    assert [d.key for d in out.dropped] == ["read"]
    assert {(t.key, t.from_minutes, t.to_minutes) for t in out.trimmed} == {
        ("dsa", 120, 30),
        ("proj", 45, 30),
    }


def test_unplaced_tasks_are_reported_with_a_reason():
    req = request(
        tasks=[
            {"key": "a", "title": "x", "minutes": 60, "priority": 1},
            {"key": "b", "title": "y", "minutes": 60, "priority": 3},
        ],
        focus_capacity=60,
        fixed=[],
    )
    tasks, context, low = to_domain(req)
    out = to_response(DAY, plan_day(tasks, context, low_energy=low))
    assert [(u.key, u.reason) for u in out.unplaced] == [("b", "over_focus_capacity")]
