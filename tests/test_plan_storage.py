import json
import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    Integer,
    Numeric,
    String,
    Uuid,
    create_engine,
    func,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Base, Goal, User
from app.db.plan_models import Plan, PlanBlock, PlanTask
from app.planning.fallback import PlanMode, plan_day
from app.planning.intervals import Interval
from app.planning.records import StoredPlanCorrupt
from app.planning.types import (
    BlockKind,
    DayContext,
    PlanError,
    PlannedBlock,
    Priority,
    TaskSpec,
)
from app.planning.validator import PlanInvalid
from app.services.plans import (
    delete_plans_for_user,
    export_plans_for_user,
    load_day_plan,
    save_day_plan,
)

DAY = date(2026, 11, 28)
OTHER_DAY = date(2026, 11, 29)
_counter = {"n": 0}


def _sample(column):
    _counter["n"] += 1
    n = _counter["n"]
    kind = column.type
    if isinstance(kind, Boolean):
        return False
    if isinstance(kind, Enum):
        return kind.enums[0]
    if isinstance(kind, String):  # also covers Text
        return f"user{n}@example.com" if "email" in column.name else f"{column.name}-{n}"
    if isinstance(kind, Integer):
        return n
    if isinstance(kind, Float | Numeric):
        return 1
    if isinstance(kind, DateTime):
        return datetime.now(UTC)
    if isinstance(kind, Date):
        return date.today()
    if isinstance(kind, Uuid):
        return uuid.uuid4()
    if isinstance(kind, JSON):
        return {}
    raise NotImplementedError(f"test helper cannot fill {column.table.name}.{column.name} ({kind})")


def make_row(session, model, **given):
    """Create a row, filling every required column this helper has not been given."""
    values = dict(given)
    for column in model.__table__.columns:
        if column.name in values:
            continue
        if column.primary_key and isinstance(column.type, Integer):
            continue
        if column.nullable or column.default is not None or column.server_default is not None:
            continue
        values[column.name] = _sample(column)
    row = model(**values)
    session.add(row)
    session.flush()
    return row


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    tables = [m.__table__ for m in (User, Goal, Plan, PlanTask, PlanBlock)]
    Base.metadata.create_all(engine, tables=tables)
    with Session(engine) as db:
        yield db
    engine.dispose()


def build_plan(goal_id=None, low_energy=False):
    tasks = [
        TaskSpec("dsa", "DSA practice", 120, priority=Priority.MUST, goal_id=goal_id),
        TaskSpec("proj", "Project work", 45),
        TaskSpec("read", "Read a paper", 30, priority=Priority.COULD),
    ]
    lecture = PlannedBlock(BlockKind.FIXED, "Lectures", Interval(540, 780))
    context = DayContext(awake=Interval(420, 1380), fixed=(lecture,))
    return tasks, plan_day(tasks, context, low_energy=low_energy)


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_plan_tables_are_registered_on_the_shared_metadata():
    assert {"plans", "plan_tasks", "plan_blocks"} <= set(Base.metadata.tables)


def test_full_plan_round_trip(session):
    user = make_row(session, User)
    tasks, plan = build_plan()
    save_day_plan(session, user.id, DAY, plan, tasks)
    stored = load_day_plan(session, user.id, DAY)
    assert stored.day_plan.mode is PlanMode.FULL
    assert stored.day_plan.schedule == plan.schedule
    assert stored.day_plan.context == plan.context
    assert sorted(t.key for t in stored.day_plan.tasks) == ["dsa", "proj", "read"]
    assert list(stored.requested) == tasks


def test_minimum_plan_round_trip_keeps_dropped_and_original_minutes(session):
    user = make_row(session, User)
    tasks, plan = build_plan(low_energy=True)
    save_day_plan(session, user.id, DAY, plan, tasks)
    stored = load_day_plan(session, user.id, DAY)
    assert stored.day_plan.mode is PlanMode.MINIMUM
    assert {d.task_key for d in stored.day_plan.dropped} == {d.task_key for d in plan.dropped}
    assert {t.task_key for t in stored.day_plan.trimmed} == {t.task_key for t in plan.trimmed}
    assert [t.minutes for t in stored.requested] == [120, 45, 30]


def test_nothing_stored_means_none(session):
    user = make_row(session, User)
    assert load_day_plan(session, user.id, DAY) is None


def test_saving_again_replaces_the_day(session):
    user = make_row(session, User)
    tasks, plan = build_plan()
    save_day_plan(session, user.id, DAY, plan, tasks)
    tasks2, plan2 = build_plan(low_energy=True)
    save_day_plan(session, user.id, DAY, plan2, tasks2)
    assert count(session, Plan) == 1
    assert count(session, PlanTask) == 3
    assert count(session, PlanBlock) == len(plan2.schedule.blocks)
    assert load_day_plan(session, user.id, DAY).day_plan.mode is PlanMode.MINIMUM


def test_users_are_isolated(session):
    alice, bob = make_row(session, User), make_row(session, User)
    tasks, plan = build_plan()
    save_day_plan(session, alice.id, DAY, plan, tasks)
    assert load_day_plan(session, bob.id, DAY) is None
    save_day_plan(session, bob.id, DAY, plan, tasks)
    assert count(session, Plan) == 2
    assert load_day_plan(session, alice.id, DAY) is not None


def test_goal_must_belong_to_the_user(session):
    alice, bob = make_row(session, User), make_row(session, User)
    bobs_goal = make_row(session, Goal, user_id=bob.id)
    tasks, plan = build_plan(goal_id=bobs_goal.id)
    with pytest.raises(PlanError):
        save_day_plan(session, alice.id, DAY, plan, tasks)
    assert count(session, Plan) == 0


def test_own_goal_is_kept(session):
    user = make_row(session, User)
    goal = make_row(session, Goal, user_id=user.id)
    tasks, plan = build_plan(goal_id=goal.id)
    save_day_plan(session, user.id, DAY, plan, tasks)
    stored = load_day_plan(session, user.id, DAY)
    assert {t.goal_id for t in stored.requested} == {goal.id, None}


def test_a_damaged_stored_plan_is_rejected_on_load(session):
    user = make_row(session, User)
    tasks, plan = build_plan()
    plan_id = save_day_plan(session, user.id, DAY, plan, tasks)
    session.execute(
        update(PlanBlock)
        .where(PlanBlock.plan_id == plan_id, PlanBlock.kind == "task")
        .values(start_minute=560, end_minute=620)
    )
    with pytest.raises((PlanInvalid, StoredPlanCorrupt)):
        load_day_plan(session, user.id, DAY)


def test_database_rejects_a_backwards_block(session):
    user = make_row(session, User)
    tasks, plan = build_plan()
    plan_id = save_day_plan(session, user.id, DAY, plan, tasks)
    session.add(PlanBlock(plan_id=plan_id, position=99, kind="task", title="x",
                          start_minute=100, end_minute=50, task_key="dsa"))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_database_allows_one_plan_per_user_per_day(session):
    user = make_row(session, User)
    tasks, plan = build_plan()
    save_day_plan(session, user.id, DAY, plan, tasks)
    session.add(Plan(user_id=user.id, plan_date=DAY, mode="full", reason="x", awake_start=0,
                     awake_end=100, focus_capacity=0, max_focus_run=30, break_minutes=0,
                     focus_minutes=0))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_delete_plans_for_user_removes_only_that_users_rows(session):
    alice, bob = make_row(session, User), make_row(session, User)
    tasks, plan = build_plan()
    save_day_plan(session, alice.id, DAY, plan, tasks)
    save_day_plan(session, alice.id, OTHER_DAY, plan, tasks)
    save_day_plan(session, bob.id, DAY, plan, tasks)
    assert delete_plans_for_user(session, alice.id) == 2
    assert load_day_plan(session, alice.id, DAY) is None
    assert load_day_plan(session, bob.id, DAY) is not None
    assert count(session, Plan) == 1
    assert count(session, PlanTask) == 3
    assert count(session, PlanBlock) == len(plan.schedule.blocks)


def test_export_is_json_safe_readable_and_scoped(session):
    alice, bob = make_row(session, User), make_row(session, User)
    tasks, plan = build_plan()
    save_day_plan(session, alice.id, DAY, plan, tasks)
    save_day_plan(session, bob.id, DAY, plan, tasks)
    data = export_plans_for_user(session, alice.id)
    json.dumps(data)
    assert len(data) == 1
    assert data[0]["date"] == "2026-11-28"
    assert data[0]["blocks"][0]["start"] == "07:00"
    assert len(data[0]["tasks"]) == 3
