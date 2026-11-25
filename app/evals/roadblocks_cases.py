"""Golden cases for roadblock detection: the activity rules and the verification of model output."""

from dataclasses import dataclass

from app.methods.taxonomy import RoadblockType as R

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


@dataclass(frozen=True)
class RuleCase:
    id: str
    execution: dict
    expected: frozenset[R]


@dataclass(frozen=True)
class VerifyCase:
    id: str
    user_text: str
    model_output: dict
    expected: dict[R, str]  # roadblock -> strength
    dropped: tuple[str, ...] = ()


RULE_CASES: list[RuleCase] = [
    RuleCase("healthy", BASE, frozenset()),
    RuleCase("phone_checks", BASE | {"unplanned_phone_checks": 28}, frozenset({R.DISTRACTION})),
    RuleCase("postponed", BASE | {"tasks_postponed_3_plus": 3}, frozenset({R.AVOIDANCE})),
    RuleCase("over_capacity", BASE | {"days_over_capacity": 4}, frozenset({R.OVERLOAD})),
    RuleCase("low_completion", BASE | {"tasks_completed": 3}, frozenset({R.UNREALISTIC_PLANNING})),
    RuleCase(
        "low_energy",
        BASE | {"energy_ratings": [2, 2, 3, 2, 2, 3, 2]},
        frozenset({R.LOW_ENERGY}),
    ),
    RuleCase(
        "long_low_energy_streak",
        BASE | {"days_covered": 14, "energy_ratings": [2] * 14, "low_energy_streak_days": 14},
        frozenset({R.LOW_ENERGY, R.BURNOUT_RISK}),
    ),
    RuleCase(
        "not_enough_data",
        BASE
        | {
            "days_covered": 3,
            "focus_blocks_planned": 3,
            "focus_blocks_completed": 1,
            "unplanned_phone_checks": 12,
            "energy_ratings": [1, 1, 1],
        },
        frozenset(),
    ),
    RuleCase(
        "several_at_once",
        BASE | {"tasks_postponed_3_plus": 3, "days_over_capacity": 4, "tasks_completed": 3},
        frozenset({R.AVOIDANCE, R.OVERLOAD, R.UNREALISTIC_PLANNING}),
    ),
    RuleCase(
        "exactly_at_thresholds",
        BASE
        | {
            "days_covered": 8,
            "unplanned_phone_checks": 21,
            "tasks_postponed_3_plus": 2,
            "days_over_capacity": 3,
            "tasks_completed": 5,
            "energy_ratings": [2, 3, 2, 3, 2, 3, 2, 3],
        },
        frozenset({R.DISTRACTION, R.AVOIDANCE, R.OVERLOAD, R.LOW_ENERGY}),
    ),
]

TEXT = (
    "My phone keeps distracting me and I keep putting off my project "
    "because I do not know where to start."
)

VERIFY_CASES: list[VerifyCase] = [
    VerifyCase(
        "grounded_quote",
        TEXT,
        {"roadblocks": [{"roadblock": "distraction", "quote": "My phone keeps distracting me"}]},
        {R.DISTRACTION: "strong"},
    ),
    VerifyCase(
        "ungrounded_quote",
        TEXT,
        {"roadblocks": [{"roadblock": "overload", "quote": "I have too many commitments"}]},
        {R.OVERLOAD: "possible"},
    ),
    VerifyCase(
        "unknown_roadblock",
        TEXT,
        {"roadblocks": [{"roadblock": "boredom", "quote": "I keep putting off my project"}]},
        {},
        ("boredom",),
    ),
    VerifyCase(
        "no_quote",
        TEXT,
        {"roadblocks": [{"roadblock": "avoidance"}]},
        {R.AVOIDANCE: "possible"},
    ),
    VerifyCase(
        "id_and_quote_normalised",
        TEXT,
        {"roadblocks": [{"roadblock": " Avoidance ", "quote": "PUTTING   off my project"}]},
        {R.AVOIDANCE: "strong"},
    ),
    VerifyCase("empty_proposal", TEXT, {"roadblocks": []}, {}),
    VerifyCase(
        "duplicate_one_grounded",
        TEXT,
        {
            "roadblocks": [
                {"roadblock": "unclear_next_step", "quote": "I do not know where to start"},
                {"roadblock": "unclear_next_step"},
            ]
        },
        {R.UNCLEAR_NEXT_STEP: "strong"},
    ),
    VerifyCase(
        "valid_plus_invalid",
        TEXT,
        {
            "roadblocks": [
                {"roadblock": "distraction", "quote": "My phone keeps distracting me"},
                {"roadblock": "laziness"},
            ]
        },
        {R.DISTRACTION: "strong"},
        ("laziness",),
    ),
]
