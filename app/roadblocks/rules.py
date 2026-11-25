"""Rule-based roadblock detection from activity data.

Thresholds are starting points, documented here and tested at their boundaries. They should be
tuned against real usage. Rules only fire when there is enough data to mean something.
"""

from dataclasses import dataclass

from app.methods.taxonomy import DESCRIPTIONS, SENSITIVE, RoadblockType
from app.schemas.roadblocks import (
    DetectedRoadblock,
    ExecutionSummary,
    Signal,
    SignalSource,
    Strength,
)


@dataclass(frozen=True)
class Thresholds:
    min_days: int = 5  # fewer days of data than this: rules are skipped
    min_blocks: int = 3  # focus blocks needed before judging phone checks
    checks_per_block: float = 3.0  # at or above: distraction
    postponed_tasks: int = 2  # tasks postponed 3+ times, at or above: avoidance
    over_capacity_days: int = 3  # days planned time exceeded available time: overload
    min_tasks: int = 5  # tasks needed before judging the completion rate
    completion_rate_low: float = 0.5  # BELOW this: unrealistic planning
    estimate_ratio_high: float = 1.5  # at or above: unrealistic planning
    min_ratings: int = 5  # energy ratings needed before judging the average
    low_energy_avg: float = 2.5  # at or BELOW this out of 5: low energy
    burnout_streak_days: int = 14  # days of low energy in a row: burnout risk


DEFAULT_THRESHOLDS = Thresholds()


def make_detection(
    roadblock: RoadblockType, signals: list[Signal], strength: Strength = Strength.STRONG
) -> DetectedRoadblock:
    return DetectedRoadblock(
        roadblock=roadblock,
        description=DESCRIPTIONS[roadblock],
        strength=strength,
        sensitive=roadblock in SENSITIVE,
        signals=signals,
    )


def detect_from_execution(
    data: ExecutionSummary, thresholds: Thresholds = DEFAULT_THRESHOLDS
) -> tuple[list[DetectedRoadblock], list[str]]:
    t = thresholds
    if data.days_covered < t.min_days:
        note = (
            f"Your activity data covers {data.days_covered} days, and at least {t.min_days} "
            "are needed, so it was not used."
        )
        return [], [note]

    found: dict[RoadblockType, list[Signal]] = {}

    def add(roadblock: RoadblockType, detail: str) -> None:
        found.setdefault(roadblock, []).append(Signal(source=SignalSource.DATA, detail=detail))

    if data.focus_blocks_planned >= t.min_blocks:
        per_block = data.unplanned_phone_checks / data.focus_blocks_planned
        if per_block >= t.checks_per_block:
            add(
                RoadblockType.DISTRACTION,
                f"{data.unplanned_phone_checks} unplanned phone checks across "
                f"{data.focus_blocks_planned} focus blocks (about {per_block:.1f} per block).",
            )

    if data.tasks_postponed_3_plus >= t.postponed_tasks:
        add(
            RoadblockType.AVOIDANCE,
            f"{data.tasks_postponed_3_plus} tasks were postponed three or more times.",
        )

    if data.days_over_capacity >= t.over_capacity_days:
        add(
            RoadblockType.OVERLOAD,
            f"Planned time was more than the time available on {data.days_over_capacity} "
            f"of {data.days_covered} days.",
        )

    if data.tasks_planned >= t.min_tasks:
        rate = data.tasks_completed / data.tasks_planned
        if rate < t.completion_rate_low:
            add(
                RoadblockType.UNREALISTIC_PLANNING,
                f"Completed {data.tasks_completed} of {data.tasks_planned} planned tasks "
                f"({rate:.0%}).",
            )
    ratio = data.avg_actual_to_estimate_ratio
    if ratio is not None and ratio >= t.estimate_ratio_high:
        add(
            RoadblockType.UNREALISTIC_PLANNING,
            f"Tasks took about {ratio:.1f} times longer than estimated.",
        )

    ratings = data.energy_ratings
    if len(ratings) >= t.min_ratings:
        average = sum(ratings) / len(ratings)
        if average <= t.low_energy_avg:
            add(
                RoadblockType.LOW_ENERGY,
                f"Average energy rating was {average:.1f} out of 5 over {len(ratings)} days.",
            )

    if data.low_energy_streak_days >= t.burnout_streak_days:
        add(
            RoadblockType.BURNOUT_RISK,
            f"Energy was low for {data.low_energy_streak_days} days in a row.",
        )

    return [make_detection(roadblock, signals) for roadblock, signals in found.items()], []
