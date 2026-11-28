"""Request and response shapes for the life intake and the obstacle list.

The answer validator is the interesting part: an answer is checked against its own
catalogue question, so a time question cannot accept prose and an int question cannot
accept a number outside its bounds. That check lives here rather than in the route,
so it is covered by unit tests and applies wherever the schema is used.
"""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.intake import questions
from app.intake.questions import QuestionGroup, QuestionKind
from app.intake.types import USER_SETTABLE_STATUSES, ObstacleSource, ObstacleStatus
from app.methods.taxonomy import RoadblockType

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class QuestionOut(BaseModel):
    """One catalogue question, as the web page receives it."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    group: QuestionGroup
    kind: QuestionKind
    prompt: str
    help_text: str | None
    required: bool
    max_length: int
    min_value: int | None
    max_value: int | None
    choices: tuple[str, ...]


class IntakeAnswerIn(BaseModel):
    """One answer, checked against the question it claims to answer."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    question_key: str = Field(min_length=1, max_length=60)
    value: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def _check_against_catalogue(self) -> "IntakeAnswerIn":
        question = questions.get(self.question_key)
        if question is None:
            raise ValueError(f"no such question: {self.question_key}")
        if len(self.value) > question.max_length:
            raise ValueError(
                f"answer to {question.key} is longer than {question.max_length} characters"
            )
        if question.kind is QuestionKind.TIME:
            if not _TIME_RE.match(self.value):
                raise ValueError(f"answer to {question.key} must be a time as HH:MM, 24-hour")
        elif question.kind is QuestionKind.INT:
            if not re.fullmatch(r"\d{1,4}", self.value):
                raise ValueError(f"answer to {question.key} must be a whole number")
            number = int(self.value)
            # The catalogue guarantees both bounds on an int question; these fallbacks
            # keep the types honest without an assert that -O would strip.
            low = question.min_value if question.min_value is not None else 0
            high = question.max_value if question.max_value is not None else 9999
            if not low <= number <= high:
                raise ValueError(f"answer to {question.key} must be between {low} and {high}")
        elif question.kind is QuestionKind.CHOICE:
            if self.value not in question.choices:
                allowed = ", ".join(question.choices)
                raise ValueError(f"answer to {question.key} must be one of: {allowed}")
        return self


class IntakeAnswerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    question_key: str
    value: str
    updated_at: datetime


class IntakeProgress(BaseModel):
    """How far through the intake the user is."""

    model_config = ConfigDict(extra="forbid")

    answered: int = Field(ge=0)
    required_total: int = Field(ge=0)
    missing_required: tuple[str, ...]
    complete: bool


class ObstacleCreate(BaseModel):
    """A problem the user says is holding them back, in their own words."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    text: str = Field(min_length=3, max_length=500)
    severity: int | None = Field(default=None, ge=1, le=5)


class ObstacleUpdate(BaseModel):
    """What the user may change by hand: how bad it is, and whether it still applies."""

    model_config = ConfigDict(extra="forbid")

    status: ObstacleStatus | None = None
    severity: int | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def _check(self) -> "ObstacleUpdate":
        if self.status is None and self.severity is None:
            raise ValueError("change the status, the severity, or both")
        if self.status is not None and self.status not in USER_SETTABLE_STATUSES:
            allowed = ", ".join(sorted(s.value for s in USER_SETTABLE_STATUSES))
            raise ValueError(f"status may only be set to one of: {allowed}")
        return self


class ObstacleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    text: str
    roadblock_type: RoadblockType | None
    status: ObstacleStatus
    source: ObstacleSource
    severity: int | None
    confidence: float
    classified_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime
