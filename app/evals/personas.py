"""Run made-up users through the whole product and score five things.

    python -m app.evals.personas

For each persona: what they say and what their data shows go through roadblock detection and
method suggestion (detection, grounding, safety), then their day goes through the planner and the
independent validator (plan constraints), then five scripted check-in days are compared with
their plan and the percentages are checked against a separate integer calculation (check-ins).

The model is scripted, so this is free, offline and the same every run. CI runs it.
"""

from dataclasses import dataclass, field

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.checkins.compare import compare_day
from app.checkins.types import BlockReason, Checkin, TaskOutcome, TaskStatus
from app.checkins.weekly import review_week
from app.db import models  # noqa: F401  (registers the tables)
from app.db.base import Base
from app.evals.personas_cases import DAYS, KIND_METRIC, PERSONAS, WEEKS, Day, Persona
from app.evals.pipeline import run_case
from app.planning.fallback import plan_day
from app.planning.intervals import Interval
from app.planning.types import BlockKind, DayContext, Effort, PlannedBlock, TaskSpec
from app.planning.validator import validate_schedule

METRICS = ("detection", "grounding", "safety", "plan constraints", "check-ins")


@dataclass
class Score:
    ok: int = 0
    total: int = 0

    def add(self, passed: bool) -> None:
        self.total += 1
        self.ok += 1 if passed else 0

    @property
    def percent(self) -> int:
        return 100 if self.total == 0 else (200 * self.ok + self.total) // (2 * self.total)


@dataclass
class PersonaReport:
    personas: int = 0
    scores: dict[str, Score] = field(default_factory=lambda: {m: Score() for m in METRICS})
    failures: list[str] = field(default_factory=list)


def _context(day: Day) -> DayContext:
    fixed = tuple(
        PlannedBlock(BlockKind.FIXED, title, Interval(start, end))
        for title, start, end in day.fixed
    )
    return DayContext(
        awake=Interval(*day.awake),
        fixed=fixed,
        focus_capacity=day.focus_capacity,
        max_focus_run=day.max_focus_run,
    )


def _planned_minutes(plan) -> dict[str, int]:
    """Minutes the planner actually placed for each task."""
    planned: dict[str, int] = {}
    for block in plan.schedule.blocks:
        if block.kind is BlockKind.TASK:
            planned[block.task_key] = planned.get(block.task_key, 0) + block.interval.length
    return planned


def _expected_percent(counted: int, planned: int) -> int:
    """Percent rounded half up, with whole numbers only (a separate check of the product)."""
    return (200 * counted + planned) // (2 * planned)


def _checkin(planned: dict[str, int], pattern: str) -> tuple[Checkin, int]:
    """A scripted day and the minutes that should count."""
    keys = sorted(planned)
    outcomes = []
    counted = 0
    for index, key in enumerate(keys):
        if pattern == "full" or (pattern == "half" and index == 0):
            outcomes.append(TaskOutcome(key, TaskStatus.DONE, planned[key], None))
            counted += planned[key]
        else:
            reason = BlockReason.TOO_TIRED if pattern == "half" else BlockReason.LOST_MOTIVATION
            outcomes.append(TaskOutcome(key, TaskStatus.SKIPPED, 0, reason))
    return Checkin(tuple(outcomes)), counted


def check_plan(persona: Persona, index: int, report: PersonaReport) -> dict[str, int] | None:
    """Plan the persona's day and validate it. Returns the placed minutes, or None."""
    day = DAYS[index % len(DAYS)]
    score = report.scores["plan constraints"]
    try:
        tasks = [
            TaskSpec(key=k, title=f"Task {k}", minutes=m, effort=Effort(e)) for k, m, e in day.tasks
        ]
        plan = plan_day(tasks, _context(day), low_energy=day.low_energy)
        violations = validate_schedule(plan.schedule, plan.tasks, plan.context)
    except Exception as error:  # an eval must report a crash, not hide it
        score.add(False)
        report.failures.append(f"{persona.id}: planning crashed: {error!r}")
        return None
    if violations:
        score.add(False)
        shown = "; ".join(f"{v.code.value}: {v.message}" for v in violations[:3])
        report.failures.append(f"{persona.id}: plan broke a rule ({shown})")
        return None
    score.add(True)
    return _planned_minutes(plan)


def check_week(
    persona: Persona, index: int, planned: dict[str, int], report: PersonaReport
) -> None:
    score = report.scores["check-ins"]
    if not planned:
        return  # nothing was placed, so there is nothing to check in on
    pattern_week = WEEKS[index % len(WEEKS)]
    total = sum(planned.values())
    day_reports = []
    ok = True
    try:
        for pattern in pattern_week:
            checkin, counted = _checkin(planned, pattern)
            day_report = compare_day(planned, checkin)
            expected = _expected_percent(counted, total)
            if day_report.adherence_percent != expected:
                ok = False
                report.failures.append(
                    f"{persona.id}: {pattern} day adherence {day_report.adherence_percent}%,"
                    f" expected {expected}%"
                )
            day_reports.append(day_report)
        if review_week(day_reports) is None:
            ok = False
            report.failures.append(f"{persona.id}: weekly review returned nothing")
    except Exception as error:
        ok = False
        report.failures.append(f"{persona.id}: check-ins crashed: {error!r}")
    score.add(ok)


def run_personas(personas: list[Persona] | None = None) -> PersonaReport:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    report = PersonaReport()
    with sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)() as db:
        for index, persona in enumerate(PERSONAS if personas is None else personas):
            report.personas += 1
            problems = run_case(persona.case, db)
            report.scores[KIND_METRIC[persona.kind]].add(not problems)
            report.failures.extend(f"{persona.id}: {p}" for p in problems)
            if persona.kind == "safety":
                continue  # after a crisis the product stops; there is no plan to check
            planned = check_plan(persona, index, report)
            if planned is not None:
                check_week(persona, index, planned, report)
    engine.dispose()
    return report


def main() -> int:
    report = run_personas()
    print("Persona eval")
    print(f"  personas             : {report.personas}")
    for name in METRICS:
        score = report.scores[name]
        print(f"  {name:<21}: {score.ok}/{score.total} ({score.percent}%)")
    for line in report.failures[:20]:
        print("  FAIL:", line)
    if len(report.failures) > 20:
        print(f"  ... and {len(report.failures) - 20} more")
    passed = not report.failures
    print("RESULT:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
