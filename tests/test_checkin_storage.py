import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.checkins.types import BlockReason, Checkin, CheckinError, TaskOutcome, TaskStatus
from app.db.checkin_models import CheckinOutcomeRow, CheckinRow
from app.db.models import Base, Goal, User
from app.db.plan_models import Plan, PlanBlock, PlanTask
from app.planning.fallback import plan_day
from app.planning.intervals import Interval
from app.planning.types import DayContext, Effort, Priority, TaskSpec
from app.services.checkins import (
    PlanNotFoundForCheckin,
    delete_checkin,
    delete_checkins_for_user,
    export_checkins_for_user,
    load_checkin,
    load_day_report,
    save_checkin,
)
from app.services.plans import delete_day_plan, delete_plans_for_user, save_day_plan

D, P, S = TaskStatus.DONE, TaskStatus.PARTIAL, TaskStatus.SKIPPED
DAY = date(2026, 11, 28)
TABLES = [
    t.__table__
    for t in (User, Goal, Plan, PlanTask, PlanBlock, CheckinRow, CheckinOutcomeRow)
]


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=TABLES)
    with Session(engine) as s:
        yield s


def make_user(session, email="a@example.com"):
    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash="x",
        is_active=True,
        consent_at=datetime.now(UTC),
    )
    session.add(user)
    session.flush()
    return user


def make_plan(session, user, plan_date=DAY):
    tasks = [
        TaskSpec("a", "Write", 30, Priority.MUST, Effort.LIGHT, None),
        TaskSpec("b", "Read", 60, Priority.SHOULD, Effort.LIGHT, None),
    ]
    context = DayContext(awake=Interval(8 * 60, 22 * 60), fixed=())
    plan = plan_day(tasks, context)
    save_day_plan(session, user.id, plan_date, plan, tasks)
    session.flush()


def sample():
    return Checkin(
        (TaskOutcome("a", D, 30), TaskOutcome("b", P, 20, BlockReason.INTERRUPTED)),
        energy=3,
        note="ok day",
    )


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_save_and_load_round_trip(session):
    user = make_user(session)
    make_plan(session, user)
    save_checkin(session, user.id, DAY, sample())
    loaded = load_checkin(session, user.id, DAY)
    assert loaded.energy == 3 and loaded.note == "ok day"
    assert {o.key: o.actual_minutes for o in loaded.outcomes} == {"a": 30, "b": 20}


def test_load_missing_is_none(session):
    user = make_user(session)
    make_plan(session, user)
    assert load_checkin(session, user.id, DAY) is None
    assert load_checkin(session, user.id, date(2026, 1, 1)) is None


def test_saving_again_replaces(session):
    user = make_user(session)
    make_plan(session, user)
    save_checkin(session, user.id, DAY, sample())
    save_checkin(session, user.id, DAY, Checkin((TaskOutcome("a", D, 25),), energy=5))
    loaded = load_checkin(session, user.id, DAY)
    assert loaded.energy == 5 and [o.key for o in loaded.outcomes] == ["a"]
    assert count(session, CheckinRow) == 1 and count(session, CheckinOutcomeRow) == 1


def test_no_plan_for_the_day(session):
    user = make_user(session)
    with pytest.raises(PlanNotFoundForCheckin):
        save_checkin(session, user.id, DAY, sample())


def test_unplanned_task_is_rejected_and_nothing_stored(session):
    user = make_user(session)
    make_plan(session, user)
    with pytest.raises(CheckinError):
        save_checkin(session, user.id, DAY, Checkin((TaskOutcome("zzz", D, 10),)))
    assert count(session, CheckinRow) == 0


def test_rejected_replacement_keeps_the_old_checkin(session):
    user = make_user(session)
    make_plan(session, user)
    save_checkin(session, user.id, DAY, sample())
    with pytest.raises(CheckinError):
        save_checkin(session, user.id, DAY, Checkin((TaskOutcome("zzz", D, 10),)))
    assert load_checkin(session, user.id, DAY).energy == 3


def test_another_user_cannot_see_or_write(session):
    owner = make_user(session, "a@example.com")
    other = make_user(session, "b@example.com")
    make_plan(session, owner)
    save_checkin(session, owner.id, DAY, sample())
    assert load_checkin(session, other.id, DAY) is None
    assert load_day_report(session, other.id, DAY) is None
    assert delete_checkin(session, other.id, DAY) is False
    with pytest.raises(PlanNotFoundForCheckin):
        save_checkin(session, other.id, DAY, sample())
    assert load_checkin(session, owner.id, DAY) is not None


def test_day_report(session):
    user = make_user(session)
    make_plan(session, user)
    assert load_day_report(session, user.id, DAY) is None
    save_checkin(session, user.id, DAY, sample())
    report = load_day_report(session, user.id, DAY)
    assert report.planned_minutes == 90 and report.counted_minutes == 50
    assert report.adherence_percent == 56 and report.unreported == ()


def test_delete_checkin(session):
    user = make_user(session)
    make_plan(session, user)
    save_checkin(session, user.id, DAY, sample())
    assert delete_checkin(session, user.id, DAY) is True
    assert delete_checkin(session, user.id, DAY) is False
    assert count(session, CheckinRow) == 0 and count(session, CheckinOutcomeRow) == 0
    assert count(session, Plan) == 1


def test_deleting_a_plan_removes_its_checkin(session):
    user = make_user(session)
    make_plan(session, user)
    save_checkin(session, user.id, DAY, sample())
    assert delete_day_plan(session, user.id, DAY) is True
    assert count(session, CheckinRow) == 0 and count(session, CheckinOutcomeRow) == 0


def test_replacing_a_plan_removes_its_old_checkin(session):
    user = make_user(session)
    make_plan(session, user)
    save_checkin(session, user.id, DAY, sample())
    make_plan(session, user)  # plan the same day again
    assert count(session, CheckinRow) == 0 and count(session, CheckinOutcomeRow) == 0


def test_deleting_all_plans_of_a_user_removes_checkins(session):
    user = make_user(session)
    make_plan(session, user)
    save_checkin(session, user.id, DAY, sample())
    delete_plans_for_user(session, user.id)
    assert count(session, CheckinRow) == 0 and count(session, CheckinOutcomeRow) == 0


def test_delete_checkins_for_user_leaves_other_users_and_plans(session):
    a = make_user(session, "a@example.com")
    b = make_user(session, "b@example.com")
    for user in (a, b):
        make_plan(session, user)
        save_checkin(session, user.id, DAY, sample())
    assert delete_checkins_for_user(session, a.id) == 1
    assert load_checkin(session, a.id, DAY) is None
    assert load_checkin(session, b.id, DAY) is not None
    assert count(session, Plan) == 2


def test_export(session):
    user = make_user(session)
    other = make_user(session, "b@example.com")
    make_plan(session, user)
    make_plan(session, other)
    save_checkin(session, user.id, DAY, sample())
    save_checkin(session, other.id, DAY, sample())
    exported = export_checkins_for_user(session, user.id)
    assert len(exported) == 1
    item = exported[0]
    assert item["date"] == "2026-11-28" and item["energy"] == 3 and item["note"] == "ok day"
    assert [o["task_key"] for o in item["outcomes"]] == ["a", "b"]
    assert item["outcomes"][1] == {
        "task_key": "b",
        "status": "partial",
        "actual_minutes": 20,
        "reason": "interrupted",
    }
    assert export_checkins_for_user(session, uuid.uuid4()) == []


def _header(session, user):
    plan = session.scalar(select(Plan).where(Plan.user_id == user.id))
    row = CheckinRow(id=uuid.uuid4(), user_id=user.id, plan_id=plan.id, energy=None, note="")
    session.add(row)
    session.flush()
    return row


def _outcome(row, **overrides):
    values = {
        "id": uuid.uuid4(),
        "checkin_id": row.id,
        "task_key": "a",
        "status": "done",
        "actual_minutes": 10,
        "reason": None,
    }
    values.update(overrides)
    return CheckinOutcomeRow(**values)


@pytest.mark.parametrize(
    "bad",
    [
        {"status": "weird"},
        {"reason": "lazy"},
        {"actual_minutes": -1},
        {"actual_minutes": 1441},
        {"status": "skipped", "actual_minutes": 0, "reason": None},
        {"status": "skipped", "actual_minutes": 5, "reason": "other"},
        {"status": "partial", "actual_minutes": 0},
        {"status": "done", "reason": "other"},
    ],
)
def test_database_rejects_invalid_outcomes(session, bad):
    user = make_user(session)
    make_plan(session, user)
    row = _header(session, user)
    session.add(_outcome(row, **bad))
    with pytest.raises(IntegrityError):
        session.flush()


def test_database_rejects_duplicate_task_in_one_checkin(session):
    user = make_user(session)
    make_plan(session, user)
    row = _header(session, user)
    session.add(_outcome(row))
    session.add(_outcome(row))
    with pytest.raises(IntegrityError):
        session.flush()


def test_database_rejects_second_checkin_for_a_plan(session):
    user = make_user(session)
    make_plan(session, user)
    _header(session, user)
    with pytest.raises(IntegrityError):
        _header(session, user)


def test_database_rejects_bad_energy(session):
    user = make_user(session)
    make_plan(session, user)
    plan = session.scalar(select(Plan).where(Plan.user_id == user.id))
    session.add(CheckinRow(id=uuid.uuid4(), user_id=user.id, plan_id=plan.id, energy=9, note=""))
    with pytest.raises(IntegrityError):
        session.flush()
