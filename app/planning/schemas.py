"""Request and response shapes for the plan API, and their conversion to and from the planner.

Pydantic checks the request at the edge. to_domain() then builds the planner's own validated
objects, so a request the planner would reject is turned into a normal 422 before any work is done.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.planning.fallback import DayPlan
from app.planning.intervals import Interval, IntervalError, format_hhmm, parse_hhmm
from app.planning.types import (
    BlockKind,
    DayContext,
    Effort,
    PlanError,
    PlannedBlock,
    Priority,
    TaskSpec,
)

MAX_TASKS = 30
MAX_FIXED = 20


def _check_time(value: str) -> str:
    try:
        parse_hhmm(value)
    except IntervalError as error:
        raise ValueError(str(error)) from error
    return value


class TaskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    title: str = Field(min_length=1, max_length=120)
    minutes: int = Field(ge=10, le=240)
    priority: int = Field(default=2, ge=1, le=3)
    effort: Literal["light", "focus"] = "focus"
    goal_id: int | uuid.UUID | None = None


class FixedBlockIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    start: str
    end: str
    kind: Literal["fixed", "sleep"] = "fixed"

    _times = field_validator("start", "end")(_check_time)


class PlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tasks: list[TaskIn] = Field(default_factory=list, max_length=MAX_TASKS)
    low_energy: bool = False
    awake_start: str = "07:00"
    awake_end: str = "23:00"
    fixed: list[FixedBlockIn] = Field(default_factory=list, max_length=MAX_FIXED)
    focus_capacity: int = Field(default=240, ge=0, le=960)
    max_focus_run: int = Field(default=90, ge=10, le=240)
    break_minutes: int = Field(default=10, ge=0, le=60)

    _times = field_validator("awake_start", "awake_end")(_check_time)

    @model_validator(mode="after")
    def _planner_accepts_this(self) -> PlanRequest:
        keys = [task.key for task in self.tasks]
        if len(set(keys)) != len(keys):
            raise ValueError("task keys must be unique")
        try:
            to_domain(self)
        except PlanError as error:
            raise ValueError(str(error)) from error
        return self


def to_domain(request: PlanRequest) -> tuple[list[TaskSpec], DayContext, bool]:
    """Build the planner's own objects. Raises PlanError for anything the planner rejects."""
    try:
        awake = Interval(parse_hhmm(request.awake_start), parse_hhmm(request.awake_end))
        fixed = tuple(
            PlannedBlock(
                BlockKind(block.kind),
                block.title,
                Interval(parse_hhmm(block.start), parse_hhmm(block.end)),
            )
            for block in request.fixed
        )
    except IntervalError as error:
        raise PlanError(str(error)) from error
    context = DayContext(
        awake=awake,
        fixed=fixed,
        focus_capacity=request.focus_capacity,
        max_focus_run=request.max_focus_run,
        break_minutes=request.break_minutes,
    )
    tasks = [
        TaskSpec(
            key=task.key,
            title=task.title,
            minutes=task.minutes,
            priority=Priority(task.priority),
            effort=Effort(task.effort),
            goal_id=task.goal_id,
        )
        for task in request.tasks
    ]
    return tasks, context, request.low_energy


class BlockOut(BaseModel):
    kind: str
    title: str
    start: str
    end: str
    task_key: str | None = None


class UnplacedOut(BaseModel):
    key: str
    reason: str
    message: str


class DroppedOut(BaseModel):
    key: str
    reason: str


class TrimmedOut(BaseModel):
    key: str
    from_minutes: int
    to_minutes: int


class PlanOut(BaseModel):
    date: date
    mode: str
    reason: str
    focus_minutes: int
    blocks: list[BlockOut]
    unplaced: list[UnplacedOut]
    dropped: list[DroppedOut]
    trimmed: list[TrimmedOut]


def to_response(plan_date: date, plan: DayPlan) -> PlanOut:
    return PlanOut(
        date=plan_date,
        mode=plan.mode.value,
        reason=plan.reason,
        focus_minutes=plan.schedule.focus_minutes,
        blocks=[
            BlockOut(
                kind=block.kind.value,
                title=block.title,
                start=format_hhmm(block.interval.start),
                end=format_hhmm(block.interval.end),
                task_key=block.task_key,
            )
            for block in plan.schedule.blocks
        ],
        unplaced=[
            UnplacedOut(key=item.task_key, reason=item.reason.value, message=item.message)
            for item in plan.schedule.unplaced
        ],
        dropped=[
            DroppedOut(key=item.task_key, reason=item.reason.value) for item in plan.dropped
        ],
        trimmed=[
            TrimmedOut(
                key=item.task_key,
                from_minutes=item.from_minutes,
                to_minutes=item.to_minutes,
            )
            for item in plan.trimmed
        ],
    )
