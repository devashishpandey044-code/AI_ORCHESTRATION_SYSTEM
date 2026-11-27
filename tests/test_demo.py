from datetime import date

import pytest

from app.checkins.schemas import CheckinRequest
from app.demo import data
from app.demo.run import DemoError, run_demo
from app.planning.schemas import PlanRequest
from app.schemas.roadblocks import ExecutionSummary

TODAY = date(2026, 11, 27)


def _quiet(_line: str) -> None:
    return None


# --- the demo data passes the real validation ---


@pytest.mark.parametrize("low_energy", [False, True])
def test_the_demo_plan_is_accepted_by_the_real_planner(low_energy):
    PlanRequest.model_validate(data.plan_body(low_energy))


def test_every_demo_checkin_is_valid_and_covers_each_task_once():
    keys = sorted(task["key"] for task in data.TASKS)
    assert len(data.CHECKINS) == 5
    for checkin in data.CHECKINS:
        CheckinRequest.model_validate(checkin)
        assert sorted(outcome["task"] for outcome in checkin["outcomes"]) == keys


def test_the_demo_activity_data_is_valid():
    ExecutionSummary.model_validate(data.EXECUTION)


def test_the_week_is_the_five_days_before_today_oldest_first():
    days = data.week_dates(TODAY)
    assert [d.isoformat() for d in days] == [
        "2026-11-22",
        "2026-11-23",
        "2026-11-24",
        "2026-11-25",
        "2026-11-26",
    ]


def test_goal_parents_always_come_before_their_children():
    for index, (_title, _horizon, parent) in enumerate(data.GOAL_CHAIN):
        assert parent is None or parent < index


# --- the whole story, through the real app ---


def test_the_whole_demo_runs_against_the_real_app(client):
    facts = run_demo(client, today=TODAY, say=_quiet)
    assert len(facts["checkin_days"]) == 5
    assert "unrealistic_planning" in [name for name, _ in facts["roadblocks"]]
    assert facts["methods"][0] == "capacity_planning_buffer"
    assert facts["usage_calls"] == 0  # roadblocks came from data, so no model was called


def test_the_demo_left_real_data_behind(client):
    run_demo(client, today=TODAY, say=_quiet)
    login = client.post(
        "/auth/login", json={"email": data.DEMO_EMAIL, "password": data.DEMO_PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    for day in data.week_dates(TODAY):
        assert client.get(f"/plans/{day.isoformat()}", headers=headers).status_code == 200
        assert client.get(f"/checkins/{day.isoformat()}", headers=headers).status_code == 200
    assert client.get(f"/plans/{TODAY.isoformat()}", headers=headers).status_code == 200
    review = client.get("/reviews/weekly?end=2026-11-26", headers=headers)
    assert review.status_code == 200


def test_running_the_demo_twice_does_not_double_anything(client):
    run_demo(client, today=TODAY, say=_quiet)
    run_demo(client, today=TODAY, say=_quiet)
    login = client.post(
        "/auth/login", json={"email": data.DEMO_EMAIL, "password": data.DEMO_PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    goals = client.get("/goals", headers=headers).json()
    goals = goals if isinstance(goals, list) else goals["items"]
    assert len(goals) == len(data.GOAL_CHAIN)
    experiments = client.get("/methods/experiments?status=active", headers=headers).json()
    experiments = experiments if isinstance(experiments, list) else experiments["items"]
    assert len(experiments) == 1


# --- a failing step stops with a clear message ---


class _Reply:
    def __init__(self, code, body=None):
        self.status_code = code
        self._body = body
        self.content = b"x" if body is not None else b""

    def json(self):
        return self._body


class _BrokenServer:
    def post(self, path, headers=None, json=None):
        if path == "/auth/login":
            return _Reply(200, {"access_token": "t"})
        if path == "/onboarding/confirm":
            return _Reply(500, {})
        return _Reply(201, {})

    def put(self, path, headers=None, json=None):
        return _Reply(500, {})

    def get(self, path, headers=None):
        return _Reply(200, [])


def test_a_failing_step_stops_the_demo_and_names_the_step():
    with pytest.raises(DemoError, match="life model"):
        run_demo(_BrokenServer(), today=TODAY, say=_quiet)


def test_a_failed_login_stops_the_demo():
    class NoLogin(_BrokenServer):
        def post(self, path, headers=None, json=None):
            return _Reply(401, {})

    with pytest.raises(DemoError, match="login"):
        run_demo(NoLogin(), today=TODAY, say=_quiet)
