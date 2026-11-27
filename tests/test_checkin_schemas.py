from datetime import date

import pytest
from pydantic import ValidationError

from app.checkins.compare import compare_day
from app.checkins.schemas import CheckinRequest, to_checkin, to_checkin_out, to_weekly_out
from app.checkins.types import BlockReason, CheckinError, TaskStatus
from app.checkins.weekly import review_week

GOOD = {
    "outcomes": [
        {"task": "a", "status": "done", "actual_minutes": 30},
        {"task": "b", "status": "partial", "actual_minutes": 20, "reason": "interrupted"},
        {"task": "c", "status": "skipped", "actual_minutes": 0, "reason": "too_tired"},
    ],
    "energy": 3,
    "note": "ok",
}

TOO_MANY = [{"task": f"t{i}", "status": "done", "actual_minutes": 5} for i in range(51)]


def test_valid_request_converts():
    c = to_checkin(CheckinRequest(**GOOD))
    assert c.energy == 3 and c.note == "ok" and len(c.outcomes) == 3
    assert c.outcomes[1].reason is BlockReason.INTERRUPTED
    assert c.outcomes[0].status is TaskStatus.DONE


def test_defaults():
    c = to_checkin(CheckinRequest(outcomes=[]))
    assert c.outcomes == () and c.energy is None and c.note == ""


@pytest.mark.parametrize(
    "patch",
    [
        {"extra": 1},
        {"energy": 0},
        {"energy": 6},
        {"energy": "3"},
        {"energy": 3.0},
        {"energy": True},
        {"note": "x" * 501},
        {"outcomes": "nope"},
        {"outcomes": [{"task": "", "status": "done", "actual_minutes": 5}]},
        {"outcomes": [{"task": "a", "status": "finished", "actual_minutes": 5}]},
        {"outcomes": [{"task": "a", "status": "done", "actual_minutes": -1}]},
        {"outcomes": [{"task": "a", "status": "done", "actual_minutes": 1441}]},
        {"outcomes": [{"task": "a", "status": "done", "actual_minutes": "5"}]},
        {"outcomes": [{"task": "a", "status": "done", "actual_minutes": 5.5}]},
        {"outcomes": [{"task": "a", "status": "done", "actual_minutes": True}]},
        {"outcomes": [{"task": "a", "status": "done", "actual_minutes": 5, "reason": "lazy"}]},
        {"outcomes": [{"task": "a", "status": "done", "actual_minutes": 5, "extra": 1}]},
        {"outcomes": [{"task": "a", "status": "done"}]},
        {"outcomes": TOO_MANY},
    ],
)
def test_field_rules_reject(patch):
    with pytest.raises(ValidationError):
        CheckinRequest(**{**GOOD, **patch})


@pytest.mark.parametrize(
    "outcome",
    [
        {"task": "a", "status": "skipped", "actual_minutes": 0},
        {"task": "a", "status": "skipped", "actual_minutes": 5, "reason": "other"},
        {"task": "a", "status": "done", "actual_minutes": 0},
        {"task": "a", "status": "done", "actual_minutes": 5, "reason": "other"},
    ],
)
def test_cross_field_rules_raise_domain_error(outcome):
    request = CheckinRequest(outcomes=[outcome])  # passes the field rules
    with pytest.raises(CheckinError):
        to_checkin(request)


def test_duplicate_task_is_a_domain_error():
    o = {"task": "a", "status": "done", "actual_minutes": 5}
    with pytest.raises(CheckinError):
        to_checkin(CheckinRequest(outcomes=[o, o]))


def test_report_output():
    checkin = to_checkin(CheckinRequest(**GOOD))
    report = compare_day({"a": 30, "b": 60, "c": 30, "d": 10}, checkin)
    out = to_checkin_out(date(2026, 11, 28), checkin, report)
    data = out.model_dump(mode="json")
    assert data["date"] == "2026-11-28" and data["energy"] == 3
    assert data["report"]["planned_minutes"] == 130
    assert data["report"]["counted_minutes"] == 50
    assert data["report"]["adherence_percent"] == 38
    assert data["report"]["unreported"] == ["d"]
    assert [t["task"] for t in data["report"]["tasks"]] == ["a", "b", "c"]
    assert data["report"]["tasks"][1]["reason"] == "interrupted"


def test_weekly_output():
    checkin = to_checkin(CheckinRequest(**GOOD))
    report = compare_day({"a": 30, "b": 60, "c": 30}, checkin)
    review = review_week([report, report, report])
    out = to_weekly_out(date(2026, 11, 22), date(2026, 11, 28), review)
    data = out.model_dump(mode="json")
    assert data["start"] == "2026-11-22" and data["end"] == "2026-11-28"
    assert data["days_with_checkins"] == 3
    assert data["planned_minutes"] == 360 and data["counted_minutes"] == 150
    assert data["adherence_percent"] == 42
    assert {r["reason"] for r in data["roadblocks"]} == {"interrupted", "too_tired"}
    codes = [s["code"] for s in data["suggestions"]]
    assert codes[0] == "plan_less" and "protect_energy" in codes and "add_buffer" in codes


def test_weekly_output_with_no_data():
    out = to_weekly_out(date(2026, 11, 22), date(2026, 11, 28), review_week([]))
    data = out.model_dump(mode="json")
    assert data["days_with_checkins"] == 0 and data["adherence_percent"] is None
    assert [s["code"] for s in data["suggestions"]] == ["need_more_data"]
