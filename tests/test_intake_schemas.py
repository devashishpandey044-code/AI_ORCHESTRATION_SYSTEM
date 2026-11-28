import pytest
from pydantic import ValidationError

from app.intake import questions
from app.intake.types import USER_SETTABLE_STATUSES, ObstacleStatus
from app.schemas.intake import (
    IntakeAnswerIn,
    ObstacleCreate,
    ObstacleUpdate,
    QuestionOut,
)


def test_a_text_answer_is_accepted_and_stripped():
    answer = IntakeAnswerIn(question_key="weekly_fixed", value="  Classes 9 to 1  ")
    assert answer.value == "Classes 9 to 1"


def test_an_unknown_question_key_is_rejected():
    with pytest.raises(ValidationError, match="no such question"):
        IntakeAnswerIn(question_key="not_a_question", value="whatever")


@pytest.mark.parametrize("value", ["07:30", "00:00", "23:59"])
def test_valid_times_are_accepted(value):
    assert IntakeAnswerIn(question_key="sleep_time", value=value).value == value


@pytest.mark.parametrize("value", ["7:30", "24:00", "23:60", "half past seven", "late", "0730"])
def test_invalid_times_are_rejected(value):
    with pytest.raises(ValidationError, match="HH:MM"):
        IntakeAnswerIn(question_key="sleep_time", value=value)


@pytest.mark.parametrize("value", ["0", "90", "720"])
def test_numbers_inside_the_bounds_are_accepted(value):
    assert IntakeAnswerIn(question_key="focus_minutes_per_day", value=value).value == value


def test_a_number_above_the_bound_is_rejected():
    with pytest.raises(ValidationError, match="between 0 and 720"):
        IntakeAnswerIn(question_key="focus_minutes_per_day", value="721")


def test_zero_days_a_week_is_rejected():
    with pytest.raises(ValidationError, match="between 1 and 7"):
        IntakeAnswerIn(question_key="focus_days_per_week", value="0")


@pytest.mark.parametrize("value", ["3.5", "-2", "lots", "90 minutes", ""])
def test_non_numbers_are_rejected_for_an_int_question(value):
    with pytest.raises(ValidationError):
        IntakeAnswerIn(question_key="focus_minutes_per_day", value=value)


def test_a_choice_answer_must_be_one_of_the_choices():
    assert IntakeAnswerIn(question_key="sleep_quality", value="poor").value == "poor"
    with pytest.raises(ValidationError, match="one of: poor, mixed, good"):
        IntakeAnswerIn(question_key="sleep_quality", value="terrible")


def test_an_answer_longer_than_the_question_allows_is_rejected():
    question = questions.get("weekly_fixed")
    with pytest.raises(ValidationError):
        IntakeAnswerIn(question_key="weekly_fixed", value="x" * (question.max_length + 1))


def test_an_empty_answer_is_rejected():
    with pytest.raises(ValidationError):
        IntakeAnswerIn(question_key="weekly_fixed", value="   ")


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        IntakeAnswerIn(question_key="weekly_fixed", value="ok", notes="sneaky")


def test_every_catalogue_question_serialises():
    out = [QuestionOut.model_validate(q) for q in questions.QUESTIONS]
    assert len(out) == len(questions.QUESTIONS)
    assert out[0].key == questions.keys()[0]


def test_an_obstacle_needs_real_text():
    assert ObstacleCreate(text="I keep scrolling at night").severity is None
    with pytest.raises(ValidationError):
        ObstacleCreate(text="x")


def test_obstacle_severity_is_bounded():
    assert ObstacleCreate(text="Too tired after labs", severity=4).severity == 4
    for bad in (0, 6):
        with pytest.raises(ValidationError):
            ObstacleCreate(text="Too tired after labs", severity=bad)


def test_an_empty_obstacle_update_is_rejected():
    with pytest.raises(ValidationError, match="status, the severity, or both"):
        ObstacleUpdate()


@pytest.mark.parametrize("status", sorted(USER_SETTABLE_STATUSES))
def test_a_user_may_set_the_open_and_closed_statuses(status):
    assert ObstacleUpdate(status=status).status is status


@pytest.mark.parametrize("status", [ObstacleStatus.STATED, ObstacleStatus.OUT_OF_SCOPE])
def test_a_user_may_not_set_the_system_statuses(status):
    # out_of_scope is the safety boundary: a user must not be able to move an obstacle
    # across it in either direction.
    with pytest.raises(ValidationError, match="status may only be set"):
        ObstacleUpdate(status=status)
