import pytest
from pydantic import ValidationError

from app.methods.taxonomy import DESCRIPTIONS
from app.methods.taxonomy import RoadblockType as R
from app.roadblocks.rules import detect_from_execution
from app.schemas.roadblocks import ExecutionSummary, SignalSource, Strength

BASE = {
    "days_covered": 7,
    "focus_blocks_planned": 7,
    "focus_blocks_completed": 5,
    "unplanned_phone_checks": 2,
    "tasks_planned": 10,
    "tasks_completed": 8,
    "tasks_postponed_3_plus": 0,
    "days_over_capacity": 0,
    "avg_actual_to_estimate_ratio": 1.1,
    "energy_ratings": [4, 3, 4, 3, 4, 4, 3],
    "low_energy_streak_days": 0,
}


def summary(**overrides):
    return ExecutionSummary(**(BASE | overrides))


def found(data):
    return {d.roadblock for d in detect_from_execution(data)[0]}


def test_healthy_data_has_no_roadblocks():
    assert found(summary()) == set()


def test_phone_checks_trigger_distraction():
    assert found(summary(unplanned_phone_checks=28)) == {R.DISTRACTION}
    # too few focus blocks to judge
    few = summary(focus_blocks_planned=2, focus_blocks_completed=1, unplanned_phone_checks=28)
    assert found(few) == set()


def test_postponed_tasks_trigger_avoidance():
    assert found(summary(tasks_postponed_3_plus=3)) == {R.AVOIDANCE}
    assert found(summary(tasks_postponed_3_plus=1)) == set()


def test_over_capacity_days_trigger_overload():
    assert found(summary(days_over_capacity=4)) == {R.OVERLOAD}
    assert found(summary(days_over_capacity=2)) == set()


def test_low_completion_and_slow_tasks_trigger_unrealistic_planning():
    assert found(summary(tasks_completed=3)) == {R.UNREALISTIC_PLANNING}
    assert found(summary(avg_actual_to_estimate_ratio=1.8)) == {R.UNREALISTIC_PLANNING}
    too_few_tasks = summary(tasks_planned=4, tasks_completed=1)
    assert found(too_few_tasks) == set()


def test_low_energy_average_triggers_low_energy():
    assert found(summary(energy_ratings=[2, 2, 3, 2, 2, 3, 2])) == {R.LOW_ENERGY}
    assert found(summary(energy_ratings=[1, 1, 1])) == set()  # too few ratings


def test_long_low_energy_streak_triggers_burnout_risk():
    low = {"days_covered": 14, "energy_ratings": [2] * 14}
    assert found(summary(low_energy_streak_days=14, **low)) == {R.LOW_ENERGY, R.BURNOUT_RISK}
    assert found(summary(low_energy_streak_days=13, **low)) == {R.LOW_ENERGY}


def test_not_enough_days_skips_rules_with_a_note():
    data = summary(
        days_covered=3,
        focus_blocks_planned=3,
        focus_blocks_completed=1,
        unplanned_phone_checks=12,
        energy_ratings=[1, 1, 1],
    )
    detections, notes = detect_from_execution(data)
    assert detections == []
    assert len(notes) == 1
    assert "3 days" in notes[0]


def test_thresholds_are_inclusive_where_documented():
    data = summary(
        days_covered=8,
        unplanned_phone_checks=21,  # exactly 3.0 per block
        tasks_postponed_3_plus=2,  # exactly the minimum
        days_over_capacity=3,  # exactly the minimum
        tasks_completed=5,  # exactly 50%, which is NOT below 50%
        energy_ratings=[2, 3, 2, 3, 2, 3, 2, 3],  # average exactly 2.5
    )
    assert found(data) == {R.DISTRACTION, R.AVOIDANCE, R.OVERLOAD, R.LOW_ENERGY}


def test_data_signals_are_strong_and_describe_the_numbers():
    detection = detect_from_execution(summary(unplanned_phone_checks=28))[0][0]
    assert detection.strength == Strength.STRONG
    assert detection.signals[0].source == SignalSource.DATA
    assert "28" in detection.signals[0].detail
    assert detection.description == DESCRIPTIONS[R.DISTRACTION]


def test_sensitive_flag_is_set_for_energy_roadblocks_only():
    low = detect_from_execution(summary(energy_ratings=[2, 2, 3, 2, 2, 3, 2]))[0][0]
    phone = detect_from_execution(summary(unplanned_phone_checks=28))[0][0]
    assert low.sensitive is True
    assert phone.sensitive is False


def test_execution_summary_validation():
    bad_inputs = [
        {"tasks_planned": 3, "tasks_completed": 5},
        {"focus_blocks_planned": 2, "focus_blocks_completed": 3},
        {"energy_ratings": [0, 3, 3, 3, 3]},
        {"energy_ratings": [6, 3, 3, 3, 3]},
        {"low_energy_streak_days": 8},
        {"days_over_capacity": 8},
        {"energy_ratings": [3] * 8},
        {"days_covered": 0},
        {"surprise_field": 1},
    ]
    for override in bad_inputs:
        with pytest.raises(ValidationError):
            ExecutionSummary(**(BASE | override))
