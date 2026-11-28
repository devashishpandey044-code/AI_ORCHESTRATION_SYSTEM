import pytest

from app.intake import questions
from app.intake.questions import Question, QuestionGroup, QuestionKind


def test_catalogue_is_not_empty_and_keys_are_unique():
    assert len(questions.QUESTIONS) >= 10
    keys = questions.keys()
    assert len(set(keys)) == len(keys)
    assert set(questions.BY_KEY) == set(keys)


def test_every_group_is_covered():
    covered = {q.group for q in questions.QUESTIONS}
    assert covered == set(QuestionGroup)


def test_get_returns_the_question_or_none():
    assert questions.get("sleep_time").kind is QuestionKind.TIME
    assert questions.get("no_such_key") is None


def test_required_keys_are_a_subset_in_asking_order():
    required = questions.required_keys()
    assert set(required) <= set(questions.keys())
    assert required == tuple(k for k in questions.keys() if k in set(required))
    assert len(required) >= 5


def test_the_capacity_numbers_are_required():
    # The planner is built from these, so the intake cannot finish without them.
    assert "focus_minutes_per_day" in questions.required_keys()
    assert "focus_days_per_week" in questions.required_keys()


def test_missing_required_and_is_complete():
    assert questions.missing_required(set()) == questions.required_keys()
    assert not questions.is_complete(set())
    assert questions.is_complete(set(questions.required_keys()))
    # Optional answers alone never complete the intake.
    optional = {q.key for q in questions.QUESTIONS if not q.required}
    assert not questions.is_complete(optional)


def test_missing_required_keeps_asking_order():
    answered = {"sleep_time", "wake_time"}
    missing = questions.missing_required(answered)
    assert "sleep_time" not in missing
    order = questions.keys()
    positions = [order.index(k) for k in missing]
    assert positions == sorted(positions)


def test_choice_questions_carry_choices_and_others_do_not():
    for q in questions.QUESTIONS:
        if q.kind is QuestionKind.CHOICE:
            assert len(q.choices) >= 2
        else:
            assert q.choices == ()


def test_int_questions_carry_both_bounds_and_others_do_not():
    for q in questions.QUESTIONS:
        if q.kind is QuestionKind.INT:
            assert q.min_value is not None and q.max_value is not None
            assert q.min_value <= q.max_value
        else:
            assert q.min_value is None and q.max_value is None


def test_questions_are_frozen():
    with pytest.raises(AttributeError):
        questions.QUESTIONS[0].prompt = "changed"


@pytest.mark.parametrize(
    "bad",
    [
        Question(key="a b", group=QuestionGroup.ENERGY, kind=QuestionKind.TEXT, prompt="x"),
        Question(key="blank", group=QuestionGroup.ENERGY, kind=QuestionKind.TEXT, prompt="  "),
        Question(
            key="one_choice",
            group=QuestionGroup.ENERGY,
            kind=QuestionKind.CHOICE,
            prompt="x",
            choices=("only",),
        ),
        Question(
            key="dupe_choice",
            group=QuestionGroup.ENERGY,
            kind=QuestionKind.CHOICE,
            prompt="x",
            choices=("a", "a"),
        ),
        Question(key="unbounded", group=QuestionGroup.ENERGY, kind=QuestionKind.INT, prompt="x"),
        Question(
            key="inverted",
            group=QuestionGroup.ENERGY,
            kind=QuestionKind.INT,
            prompt="x",
            min_value=5,
            max_value=1,
        ),
        Question(
            key="text_with_choices",
            group=QuestionGroup.ENERGY,
            kind=QuestionKind.TEXT,
            prompt="x",
            choices=("a", "b"),
        ),
        Question(
            key="text_with_bounds",
            group=QuestionGroup.ENERGY,
            kind=QuestionKind.TEXT,
            prompt="x",
            min_value=1,
        ),
    ],
)
def test_a_malformed_catalogue_is_rejected(bad):
    with pytest.raises(ValueError):
        questions._validate_catalogue((bad,))


def test_duplicate_keys_are_rejected():
    one = questions.QUESTIONS[0]
    with pytest.raises(ValueError, match="duplicate"):
        questions._validate_catalogue((one, one))
