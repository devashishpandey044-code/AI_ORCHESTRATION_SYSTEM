"""Golden cases for method retrieval. Each names the method a person would expect to see."""

from dataclasses import dataclass

from app.methods.taxonomy import RoadblockType as R


@dataclass(frozen=True)
class RetrievalCase:
    id: str
    roadblocks: tuple[R, ...]
    situation: str
    expected_slug: str


CASES: list[RetrievalCase] = [
    RetrievalCase(
        "phone",
        (R.DISTRACTION,),
        "My phone keeps buzzing and I check it every few minutes while studying",
        "phone_friction",
    ),
    RetrievalCase(
        "big_project",
        (R.AVOIDANCE, R.UNCLEAR_NEXT_STEP),
        "The project feels huge and I do not know where to begin so I keep putting it off",
        "task_decomposition",
    ),
    RetrievalCase(
        "forget_to_start",
        (R.AVOIDANCE,),
        "I plan to start at a certain time but I forget and never begin the task",
        "implementation_intentions",
    ),
    RetrievalCase(
        "overloaded",
        (R.OVERLOAD, R.BURNOUT_RISK),
        "Too many deadlines this week and I feel exhausted",
        "minimum_viable_day",
    ),
    RetrievalCase(
        "planning",
        (R.UNREALISTIC_PLANNING,),
        "My plans always take longer than I expect and I never finish my list",
        "capacity_planning_buffer",
    ),
    RetrievalCase(
        "rereading",
        (R.INEFFECTIVE_LEARNING,),
        "I reread my notes again and again but forget everything in the exam",
        "practice_testing",
    ),
    RetrievalCase(
        "tired",
        (R.LOW_ENERGY,),
        "I feel tired by the afternoon and I scroll my phone during breaks",
        "deliberate_recovery_breaks",
    ),
    RetrievalCase(
        "focus_block",
        (R.DISTRACTION, R.AVOIDANCE),
        "I need a fixed block to work on one thing without switching",
        "protected_focus_block",
    ),
]
