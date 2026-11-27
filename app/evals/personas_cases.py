"""Made-up users for the persona eval: what they say, what their data shows, how their day looks.

Each persona is one PipelineCase (words and data in, roadblocks out, model scripted) plus the
shape of a planning day. The model is scripted on purpose: the point is to check what the CODE
does with whatever the model says, including when it makes things up.
"""

from dataclasses import dataclass

from app.evals.pipeline_cases import CALM_TEXT, CRISIS_LONG, HEALTHY, PHONE_TEXT, PipelineCase
from app.methods.taxonomy import RoadblockType as R

# Metric each kind of persona counts towards.
KIND_METRIC = {
    "detect": "detection",
    "data": "detection",
    "agree": "detection",
    "down": "detection",
    "none": "detection",
    "grounding": "grounding",
    "safety": "safety",
}


@dataclass(frozen=True)
class Day:
    """One planning day: tasks are (key, minutes, effort); fixed are (title, start, end)."""

    tasks: tuple[tuple[str, int, str], ...]
    fixed: tuple[tuple[str, int, int], ...] = ()
    awake: tuple[int, int] = (420, 1380)
    focus_capacity: int = 240
    max_focus_run: int = 90
    low_energy: bool = False


@dataclass(frozen=True)
class Persona:
    id: str
    kind: str
    case: PipelineCase


DAYS = (
    Day(
        tasks=(("study", 90, "focus"), ("report", 60, "focus"), ("email", 30, "light")),
        fixed=(("Lectures", 540, 780),),
    ),
    Day(
        tasks=(
            ("a", 120, "focus"),
            ("b", 120, "focus"),
            ("c", 90, "focus"),
            ("d", 60, "light"),
            ("e", 30, "light"),
        ),
    ),
    Day(tasks=(("rest_task", 45, "light"), ("read", 30, "light")), low_energy=True),
    Day(
        tasks=(("short", 60, "focus"), ("tiny", 30, "light")),
        awake=(420, 600),
        focus_capacity=60,
    ),
    Day(
        tasks=(("project", 150, "focus"), ("notes", 40, "light")),
        fixed=(("Lab", 600, 720), ("Gym", 1080, 1140)),
        focus_capacity=180,
        max_focus_run=60,
    ),
)

# Five check-in days per persona: full = everything done, half = first task only, none = nothing.
WEEKS = (
    ("full", "full", "half", "full", "half"),
    ("half", "none", "half", "none", "full"),
    ("full", "full", "full", "full", "full"),
)


def _text(pid, kind, text, roadblock, quote, strength="strong", **extra) -> Persona:
    case = PipelineCase(
        id=pid,
        text=text,
        model_output={"roadblocks": [{"roadblock": roadblock.value, "quote": quote}]},
        expect_roadblocks={roadblock: strength},
        expect_model_calls=1,
        **extra,
    )
    return Persona(pid, kind, case)


def _data(pid, execution, expect, kind="data", **extra) -> Persona:
    case = PipelineCase(
        id=pid, execution=execution, expect_roadblocks=expect, expect_model_calls=0, **extra
    )
    return Persona(pid, kind, case)


def _safety(pid, text, execution=None) -> Persona:
    case = PipelineCase(
        id=pid, text=text, execution=execution, expect_safety=True, expect_model_calls=0
    )
    return Persona(pid, "safety", case)


PERSONAS: list[Persona] = [
    # Words only, quote really is in the text: the claim is strong.
    _text("phone_buzzing", "detect", PHONE_TEXT, R.DISTRACTION, "My phone keeps buzzing"),
    _text(
        "instagram_pull",
        "detect",
        "Instagram notifications pull me away every few minutes when I try to code",
        R.DISTRACTION,
        "Instagram notifications pull me away",
    ),
    _text(
        "youtube_loop",
        "detect",
        "I keep opening YouTube instead of finishing my assignment",
        R.DISTRACTION,
        "I keep opening YouTube",
    ),
    _text(
        "noisy_and_phone",
        "detect",
        "My roommate plays music and my phone make it impossible to focus",
        R.DISTRACTION,
        "my phone make it impossible to focus",
    ),
    _text(
        "lab_report_delay",
        "detect",
        "I keep putting off my lab report because it feels boring",
        R.AVOIDANCE,
        "I keep putting off my lab report",
    ),
    _text(
        "resume_avoided",
        "detect",
        "I have been avoiding my resume for three weeks now",
        R.AVOIDANCE,
        "avoiding my resume",
    ),
    _text(
        "no_starting_point",
        "detect",
        "I do not know where to begin with my final year project",
        R.UNCLEAR_NEXT_STEP,
        "do not know where to begin",
    ),
    _text(
        "exam_pileup",
        "detect",
        "I have four exams and two submissions due in the same week",
        R.OVERLOAD,
        "four exams and two submissions",
    ),
    _text(
        "noisy_hostel",
        "detect",
        "My hostel room is noisy all evening and I cannot study there",
        R.POOR_ENVIRONMENT,
        "My hostel room is noisy",
    ),
    _text(
        "twelve_hour_plans",
        "detect",
        "I plan twelve hours of work every day and finish almost none of it",
        R.UNREALISTIC_PLANNING,
        "I plan twelve hours of work every day",
    ),
    _text(
        "rereading_notes",
        "detect",
        "I highlight my textbook and read it again before every test but forget it",
        R.INEFFECTIVE_LEARNING,
        "highlight my textbook",
    ),
    _text(
        "worn_out",
        "detect",
        "I am exhausted every single day and nothing feels worth the effort",
        R.LOW_ENERGY,
        "I am exhausted every single day",
        expect_detection_care_note=True,
    ),
    # Grounding: the model claims something the words do not support, or invents a category.
    _text(
        "ungrounded_overload",
        "grounding",
        "I have so much going on this week and I do not know how I will cope",
        R.OVERLOAD,
        "too many commitments",
        strength="possible",
    ),
    _text(
        "ungrounded_distraction",
        "grounding",
        "Exams are close and I feel behind on everything",
        R.DISTRACTION,
        "my phone ruins every session",
        strength="possible",
    ),
    _text(
        "ungrounded_avoidance",
        "grounding",
        "I want to do better this semester than the last one",
        R.AVOIDANCE,
        "I never start anything",
        strength="possible",
    ),
    _text(
        "ungrounded_learning",
        "grounding",
        "The syllabus is long and the exam is in two weeks",
        R.INEFFECTIVE_LEARNING,
        "nothing I study stays in my head",
        strength="possible",
    ),
    Persona(
        "invented_laziness",
        "grounding",
        PipelineCase(
            id="invented_laziness",
            text=PHONE_TEXT,
            model_output={
                "roadblocks": [
                    {"roadblock": "distraction", "quote": "My phone keeps buzzing"},
                    {"roadblock": "laziness", "quote": "I am lazy"},
                ]
            },
            expect_roadblocks={R.DISTRACTION: "strong"},
            expect_note_contains=("laziness",),
            expect_model_calls=1,
        ),
    ),
    Persona(
        "invented_stress",
        "grounding",
        PipelineCase(
            id="invented_stress",
            text=PHONE_TEXT,
            model_output={
                "roadblocks": [
                    {"roadblock": "distraction", "quote": "My phone keeps buzzing"},
                    {"roadblock": "stress", "quote": "I am stressed"},
                ]
            },
            expect_roadblocks={R.DISTRACTION: "strong"},
            expect_note_contains=("stress",),
            expect_model_calls=1,
        ),
    ),
    # Data only: no words, no model call.
    _data("data_phone_checks", HEALTHY | {"unplanned_phone_checks": 30}, {R.DISTRACTION: "strong"}),
    _data("data_postponing", HEALTHY | {"tasks_postponed_3_plus": 3}, {R.AVOIDANCE: "strong"}),
    _data("data_overcapacity", HEALTHY | {"days_over_capacity": 4}, {R.OVERLOAD: "strong"}),
    _data(
        "data_planning_gap",
        HEALTHY | {"tasks_completed": 3, "avg_actual_to_estimate_ratio": 1.8},
        {R.UNREALISTIC_PLANNING: "strong"},
    ),
    _data(
        "data_low_energy",
        HEALTHY | {"energy_ratings": [2, 2, 3, 2, 2, 2, 2]},
        {R.LOW_ENERGY: "strong"},
        expect_detection_care_note=True,
    ),
    # Nothing to find, and too little data to judge.
    _data("data_all_healthy", HEALTHY, {}, kind="none"),
    _data(
        "data_too_short",
        HEALTHY
        | {
            "days_covered": 3,
            "focus_blocks_planned": 3,
            "focus_blocks_completed": 2,
            "unplanned_phone_checks": 40,
            "tasks_planned": 4,
            "tasks_completed": 3,
            "energy_ratings": [4, 3, 4],
        },
        {},
        kind="none",
        expect_note_contains=("at least 5 are needed",),
    ),
    Persona(
        "calm_words",
        "none",
        PipelineCase(
            id="calm_words",
            text=CALM_TEXT,
            model_output={"roadblocks": []},
            expect_roadblocks={},
            expect_model_calls=1,
        ),
    ),
    # Words and data agree.
    _text(
        "phone_words_and_data",
        "agree",
        PHONE_TEXT,
        R.DISTRACTION,
        "My phone keeps buzzing",
        execution=HEALTHY | {"unplanned_phone_checks": 28},
    ),
    _text(
        "avoidance_words_and_data",
        "agree",
        "I keep putting off my lab report because it feels boring",
        R.AVOIDANCE,
        "I keep putting off my lab report",
        execution=HEALTHY | {"tasks_postponed_3_plus": 3},
    ),
    # The model is down: the data still works and the user is told.
    Persona(
        "model_down_phone",
        "down",
        PipelineCase(
            id="model_down_phone",
            text=PHONE_TEXT,
            execution=HEALTHY | {"unplanned_phone_checks": 28},
            model_fails=True,
            expect_roadblocks={R.DISTRACTION: "strong"},
            expect_note_contains=("unavailable",),
        ),
    ),
    Persona(
        "model_down_postponing",
        "down",
        PipelineCase(
            id="model_down_postponing",
            text="I keep putting off my lab report because it feels boring",
            execution=HEALTHY | {"tasks_postponed_3_plus": 3},
            model_fails=True,
            expect_roadblocks={R.AVOIDANCE: "strong"},
            expect_note_contains=("unavailable",),
        ),
    ),
    # Safety: the model is never called and nothing else runs.
    _safety("crisis_short", "I want to die"),
    _safety("crisis_long", CRISIS_LONG),
    _safety("crisis_with_data", CRISIS_LONG, HEALTHY | {"unplanned_phone_checks": 28}),
    _safety("crisis_mixed_case", "Honestly, I WANT TO DIE"),
]
