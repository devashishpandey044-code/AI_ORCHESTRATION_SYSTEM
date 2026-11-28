"""The life-intake question catalogue.

Pure data and pure functions: no database, no model call, no FastAPI. This module is
the only source of truth for which question keys exist, so an answer whose key is not
here is rejected before it reaches the database.

Wording matters here. Each prompt asks for one thing, in plain words, and the
history questions ask what the user already tried: that answer is the most
informative one in the set, because it says which advice is already spent.
"""

import enum
from dataclasses import dataclass


class QuestionKind(enum.StrEnum):
    TEXT = "text"  # free prose, kept verbatim; extraction may read it later
    TIME = "time"  # "HH:MM", 24-hour, in the user's own day
    INT = "int"  # a whole number, bounded by min_value and max_value
    CHOICE = "choice"  # exactly one of `choices`


class QuestionGroup(enum.StrEnum):
    FIXED_REALITY = "fixed_reality"
    ENERGY = "energy"
    DIRECTION = "direction"
    HISTORY = "history"
    CONSTRAINTS = "constraints"
    CAPACITY = "capacity"


@dataclass(frozen=True, slots=True)
class Question:
    key: str
    group: QuestionGroup
    kind: QuestionKind
    prompt: str
    help_text: str | None = None
    required: bool = True
    max_length: int = 2000
    min_value: int | None = None
    max_value: int | None = None
    choices: tuple[str, ...] = ()


QUESTIONS: tuple[Question, ...] = (
    Question(
        key="weekly_fixed",
        group=QuestionGroup.FIXED_REALITY,
        kind=QuestionKind.TEXT,
        prompt="What is already fixed in a normal week?",
        help_text="Classes, labs, work shifts, commute, duties at home. Include the times.",
    ),
    Question(
        key="sleep_time",
        group=QuestionGroup.FIXED_REALITY,
        kind=QuestionKind.TIME,
        prompt="What time do you usually get to sleep?",
    ),
    Question(
        key="wake_time",
        group=QuestionGroup.FIXED_REALITY,
        kind=QuestionKind.TIME,
        prompt="What time do you usually wake up?",
    ),
    Question(
        key="peak_hours",
        group=QuestionGroup.ENERGY,
        kind=QuestionKind.TEXT,
        prompt="When in the day do you think most clearly?",
        help_text="A rough window is enough, for example 'early morning' or 'after 9pm'.",
    ),
    Question(
        key="slump_hours",
        group=QuestionGroup.ENERGY,
        kind=QuestionKind.TEXT,
        prompt="When does your energy usually drop?",
    ),
    Question(
        key="sleep_quality",
        group=QuestionGroup.ENERGY,
        kind=QuestionKind.CHOICE,
        prompt="How well have you been sleeping lately?",
        choices=("poor", "mixed", "good"),
    ),
    Question(
        key="goals_six_months",
        group=QuestionGroup.DIRECTION,
        kind=QuestionKind.TEXT,
        prompt="What are two or three things you want to be true in six months?",
        help_text="Concrete beats grand. 'Comfortable with graphs and DP' beats 'be good at DSA'.",
    ),
    Question(
        key="goal_why",
        group=QuestionGroup.DIRECTION,
        kind=QuestionKind.TEXT,
        prompt="Why do those matter to you?",
        required=False,
    ),
    Question(
        key="tried_before",
        group=QuestionGroup.HISTORY,
        kind=QuestionKind.TEXT,
        prompt="What have you already tried to get organised?",
        help_text="Apps, timetables, study groups, waking up at 5am. Anything counts.",
    ),
    Question(
        key="what_stopped",
        group=QuestionGroup.HISTORY,
        kind=QuestionKind.TEXT,
        prompt="Why did it stop working?",
        help_text="The most useful answer in this whole set, so be blunt.",
        required=False,
    ),
    Question(
        key="hard_deadlines",
        group=QuestionGroup.CONSTRAINTS,
        kind=QuestionKind.TEXT,
        prompt="Any fixed dates coming up?",
        help_text="Exams, submissions, interviews, trips.",
        required=False,
    ),
    Question(
        key="limits",
        group=QuestionGroup.CONSTRAINTS,
        kind=QuestionKind.TEXT,
        prompt="Is there anything that limits what you can plan?",
        help_text="Travel, duties at home, anything physical. Only what you want to share.",
        required=False,
    ),
    Question(
        key="focus_minutes_per_day",
        group=QuestionGroup.CAPACITY,
        kind=QuestionKind.INT,
        prompt="On a normal day, how many minutes of genuinely focused work can you do?",
        help_text="Be honest rather than ambitious. The plan is built from this number.",
        min_value=0,
        max_value=720,
    ),
    Question(
        key="focus_days_per_week",
        group=QuestionGroup.CAPACITY,
        kind=QuestionKind.INT,
        prompt="How many days a week do you expect to do focused work?",
        min_value=1,
        max_value=7,
    ),
    Question(
        key="biggest_obstacle",
        group=QuestionGroup.CAPACITY,
        kind=QuestionKind.TEXT,
        prompt="In one sentence, what gets in the way most?",
        help_text="This one seeds your obstacle list, so plain words are better than tidy ones.",
    ),
)


def _validate_catalogue(questions: tuple[Question, ...]) -> None:
    """Fail at import time rather than at runtime if the catalogue is malformed."""
    seen: set[str] = set()
    for q in questions:
        if q.key in seen:
            raise ValueError(f"duplicate question key: {q.key}")
        seen.add(q.key)
        if not q.key.isidentifier():
            raise ValueError(f"question key is not a plain identifier: {q.key}")
        if not q.prompt.strip():
            raise ValueError(f"question {q.key} has no prompt")
        if q.max_length < 1:
            raise ValueError(f"question {q.key} has a non-positive max_length")
        if q.kind is QuestionKind.CHOICE:
            if len(q.choices) < 2:
                raise ValueError(f"choice question {q.key} needs at least two choices")
            if len(set(q.choices)) != len(q.choices):
                raise ValueError(f"choice question {q.key} has duplicate choices")
        elif q.choices:
            raise ValueError(f"question {q.key} has choices but is not a choice question")
        if q.kind is QuestionKind.INT:
            if q.min_value is None or q.max_value is None:
                raise ValueError(f"int question {q.key} needs both bounds")
            if q.min_value > q.max_value:
                raise ValueError(f"int question {q.key} has min_value above max_value")
        elif q.min_value is not None or q.max_value is not None:
            raise ValueError(f"question {q.key} has bounds but is not an int question")


_validate_catalogue(QUESTIONS)

BY_KEY: dict[str, Question] = {q.key: q for q in QUESTIONS}


def get(key: str) -> Question | None:
    """The question with this key, or None if the catalogue has no such key."""
    return BY_KEY.get(key)


def keys() -> tuple[str, ...]:
    """Every question key, in the order the intake asks them."""
    return tuple(q.key for q in QUESTIONS)


def required_keys() -> tuple[str, ...]:
    """The keys the user must answer before the intake counts as complete."""
    return tuple(q.key for q in QUESTIONS if q.required)


def missing_required(answered: set[str]) -> tuple[str, ...]:
    """Required keys not yet in `answered`, in asking order."""
    return tuple(k for k in required_keys() if k not in answered)


def is_complete(answered: set[str]) -> bool:
    """True once every required question has an answer."""
    return not missing_required(answered)
