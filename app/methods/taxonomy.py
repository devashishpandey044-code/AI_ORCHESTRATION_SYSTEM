import enum


class RoadblockType(enum.StrEnum):
    DISTRACTION = "distraction"
    AVOIDANCE = "avoidance"
    OVERLOAD = "overload"
    UNCLEAR_NEXT_STEP = "unclear_next_step"
    POOR_ENVIRONMENT = "poor_environment"
    UNREALISTIC_PLANNING = "unrealistic_planning"
    LOW_ENERGY = "low_energy"
    BURNOUT_RISK = "burnout_risk"
    INEFFECTIVE_LEARNING = "ineffective_learning"


DESCRIPTIONS: dict[RoadblockType, str] = {
    RoadblockType.DISTRACTION: "Attention keeps getting pulled away by phones, feeds or noise.",
    RoadblockType.AVOIDANCE: "Putting off a task that feels hard, boring or uncomfortable.",
    RoadblockType.OVERLOAD: "More commitments or tasks than the available time and energy.",
    RoadblockType.UNCLEAR_NEXT_STEP: "Not knowing what to do next, so nothing gets started.",
    RoadblockType.POOR_ENVIRONMENT: (
        "The place or setup makes focused work harder than it should be."
    ),
    RoadblockType.UNREALISTIC_PLANNING: (
        "Plans that regularly assume more time or energy than exist."
    ),
    RoadblockType.LOW_ENERGY: "Tiredness or low energy that limits what a day can hold.",
    RoadblockType.BURNOUT_RISK: "Sustained exhaustion or strain that rest alone has not fixed.",
    RoadblockType.INEFFECTIVE_LEARNING: "Study time that is not turning into learning or recall.",
}

# Roadblocks that touch wellbeing. Methods for these must carry an escalation note.
SENSITIVE: frozenset[RoadblockType] = frozenset(
    {RoadblockType.LOW_ENERGY, RoadblockType.BURNOUT_RISK}
)
