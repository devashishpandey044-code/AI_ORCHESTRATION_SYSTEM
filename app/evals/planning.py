"""Planning eval: golden days, validator tamper checks, and a large random sweep.

Run with:  python -m app.evals.planning
It fails (exit 1) if any gate case is wrong. Known gaps are listed but do not gate.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, replace

from app.planning.fallback import PlanMode, plan_day
from app.planning.intervals import Interval
from app.planning.scheduler import Schedule, Unplaced, UnplacedReason, build_schedule
from app.planning.types import (
    BlockKind,
    DayContext,
    Effort,
    PlannedBlock,
    Priority,
    TaskSpec,
)
from app.planning.validator import ViolationCode, validate_schedule

AWAKE = Interval(420, 1380)  # 07:00 to 23:00
LECTURES = PlannedBlock(BlockKind.FIXED, "Lectures", Interval(540, 780))  # 09:00 to 13:00
SWEEP_DAYS = 1000

KNOWN_GAPS = [
    "earliest_fit: mornings fill first even if the user focuses best in the evening",
    "no_deadlines: a task cannot say 'must finish by 18:00' yet",
    "no_dependencies: task B cannot be required to come after task A yet",
]


def _task(key, minutes, **kwargs):
    return TaskSpec(key=key, title=f"Task {key}", minutes=minutes, **kwargs)


def _shape(schedule: Schedule) -> list[tuple[int, int, str]]:
    return [(b.interval.start, b.interval.end, b.kind.value) for b in schedule.blocks]


# ---- golden cases: expected plans worked out by hand --------------------------------------
def _golden_cases():
    cases = []

    cases.append(
        ("empty day", [], DayContext(awake=AWAKE), False, "full", [], [])
    )
    cases.append(
        (
            "one focus task gets a break",
            [_task("a", 60)],
            DayContext(awake=AWAKE),
            False,
            "full",
            [(420, 480, "task"), (480, 490, "break")],
            [],
        )
    )
    cases.append(
        (
            "light task needs no break",
            [_task("a", 30, effort=Effort.LIGHT)],
            DayContext(awake=AWAKE),
            False,
            "full",
            [(420, 450, "task")],
            [],
        )
    )
    # 09:00-13:00 lectures; a 120-minute focus task is cut into 2 x 60 and flows around them.
    cases.append(
        (
            "long task splits around lectures",
            [_task("dsa", 120, priority=Priority.MUST)],
            DayContext(awake=AWAKE, fixed=(LECTURES,), max_focus_run=90),
            False,
            "full",
            [
                (420, 480, "task"),
                (480, 490, "break"),
                (540, 780, "fixed"),
                (780, 840, "task"),
                (840, 850, "break"),
            ],
            [],
        )
    )
    cases.append(
        (
            "focus limit leaves the lowest priority out",
            [_task("hi", 60, priority=Priority.MUST), _task("lo", 60, priority=Priority.COULD)],
            DayContext(awake=AWAKE, focus_capacity=60),
            False,
            "full",
            [(420, 480, "task"), (480, 490, "break")],
            ["lo"],
        )
    )
    cases.append(
        (
            "low energy day keeps two shortened tasks",
            [
                _task("a", 120, priority=Priority.MUST),
                _task("b", 90),
                _task("c", 60, priority=Priority.COULD),
            ],
            DayContext(awake=AWAKE, fixed=(LECTURES,)),
            True,
            "minimum",
            [
                (420, 450, "task"),
                (450, 460, "break"),
                (460, 490, "task"),
                (490, 500, "break"),
                (540, 780, "fixed"),
            ],
            [],
        )
    )
    cases.append(
        (
            "must-do that cannot fit falls back to a smaller day",
            [_task(f"m{i}", 60, priority=Priority.MUST) for i in range(3)],
            DayContext(awake=Interval(420, 540), focus_capacity=120),
            False,
            "minimum",
            [(420, 450, "task"), (450, 460, "break"), (460, 490, "task"), (490, 500, "break")],
            [],
        )
    )
    return cases


def _check_golden() -> list[str]:
    failures = []
    for name, tasks, context, low_energy, mode, shape, unplaced in _golden_cases():
        plan = plan_day(tasks, context, low_energy=low_energy)
        got_unplaced = [u.task_key for u in plan.schedule.unplaced]
        if plan.mode.value != mode:
            failures.append(f"{name}: mode {plan.mode.value}, expected {mode}")
        elif _shape(plan.schedule) != shape:
            failures.append(f"{name}: blocks {_shape(plan.schedule)}, expected {shape}")
        elif got_unplaced != unplaced:
            failures.append(f"{name}: unplaced {got_unplaced}, expected {unplaced}")
    return failures


# ---- tamper checks: the validator must notice each kind of corruption ---------------------
def _tamper_cases():
    context = DayContext(awake=AWAKE, fixed=(LECTURES,), focus_capacity=240)
    tasks = [_task("a", 60), _task("b", 120), _task("c", 30, effort=Effort.LIGHT)]
    good = build_schedule(tasks, context)

    def with_blocks(blocks):
        return replace(good, blocks=tuple(sorted(blocks, key=lambda b: b.interval)))

    def edit(predicate, change):
        return with_blocks([change(b) if predicate(b) else b for b in good.blocks])

    break_in_lecture = PlannedBlock(BlockKind.BREAK, "Break", Interval(550, 570))
    late = PlannedBlock(BlockKind.BREAK, "Break", Interval(1400, 1420))
    ghost = PlannedBlock(BlockKind.TASK, "Ghost", Interval(1200, 1230), task_key="zzz")
    fake_fixed = PlannedBlock(BlockKind.FIXED, "Surprise", Interval(1300, 1330))

    return [
        (ViolationCode.OVERLAP, with_blocks([*good.blocks, break_in_lecture]), tasks, context),
        (ViolationCode.OUTSIDE_AWAKE, with_blocks([*good.blocks, late]), tasks, context),
        (ViolationCode.FIXED_CHANGED, with_blocks([*good.blocks, fake_fixed]), tasks, context),
        (
            ViolationCode.TASK_MINUTES_MISMATCH,
            edit(
                lambda b: b.task_key == "c",
                lambda b: replace(b, interval=Interval(b.interval.start, b.interval.end - 10)),
            ),
            tasks,
            context,
        ),
        (ViolationCode.UNKNOWN_TASK, with_blocks([*good.blocks, ghost]), tasks, context),
        (
            ViolationCode.FOCUS_MINUTES_WRONG,
            replace(good, focus_minutes=good.focus_minutes + 5),
            tasks,
            context,
        ),
        (
            ViolationCode.TASK_ACCOUNTING,
            replace(good, unplaced=(Unplaced("a", UnplacedReason.NO_SPACE, "x"),)),
            tasks,
            context,
        ),
        (
            ViolationCode.BACK_TO_BACK_FOCUS,
            Schedule(
                blocks=(
                    PlannedBlock(BlockKind.TASK, "Task a", Interval(420, 480), task_key="a"),
                    PlannedBlock(BlockKind.TASK, "Task b", Interval(480, 540), task_key="b"),
                ),
                unplaced=(),
                focus_minutes=120,
            ),
            [_task("a", 60), _task("b", 60)],
            DayContext(awake=AWAKE, break_minutes=10),
        ),
        (
            ViolationCode.FOCUS_RUN_TOO_LONG,
            Schedule(
                blocks=(
                    PlannedBlock(BlockKind.TASK, "Task a", Interval(420, 540), task_key="a"),
                ),
                unplaced=(),
                focus_minutes=120,
            ),
            [_task("a", 120)],
            DayContext(awake=AWAKE, max_focus_run=60),
        ),
        (
            ViolationCode.FOCUS_OVER_CAPACITY,
            Schedule(
                blocks=(
                    PlannedBlock(BlockKind.TASK, "Task a", Interval(420, 510), task_key="a"),
                ),
                unplaced=(),
                focus_minutes=90,
            ),
            [_task("a", 90)],
            DayContext(awake=AWAKE, focus_capacity=60),
        ),
    ]


def _check_tampering() -> tuple[int, int, list[str]]:
    cases = _tamper_cases()
    failures = []
    caught = 0
    for expected, schedule, tasks, context in cases:
        codes = {v.code for v in validate_schedule(schedule, tasks, context)}
        if expected in codes:
            caught += 1
        else:
            failures.append(f"tampering not caught: {expected.value}")
    return caught, len(cases), failures


# ---- random sweep: every generated day must produce a valid plan ---------------------------
def _random_day(rng: random.Random):
    fixed, cursor = [], 420
    for _ in range(rng.randrange(0, 4)):
        start = cursor + rng.randrange(0, 120)
        end = start + rng.randrange(30, 120)
        if end > 1380:
            break
        fixed.append(PlannedBlock(BlockKind.FIXED, "Class", Interval(start, end)))
        cursor = end
    context = DayContext(
        awake=AWAKE,
        fixed=tuple(fixed),
        focus_capacity=rng.choice([0, 60, 120, 240, 360]),
        max_focus_run=rng.choice([30, 60, 90]),
        break_minutes=rng.choice([0, 5, 10, 15]),
    )
    tasks = [
        _task(
            f"t{i}",
            rng.randrange(10, 241),
            priority=rng.choice(list(Priority)),
            effort=rng.choice(list(Effort)),
        )
        for i in range(rng.randrange(0, 9))
    ]
    return tasks, context


def _check_sweep() -> tuple[int, int, list[str]]:
    rng = random.Random(2026)
    failures = []
    minimum_days = 0
    for index in range(SWEEP_DAYS):
        tasks, context = _random_day(rng)
        low_energy = rng.random() < 0.25
        plan = plan_day(tasks, context, low_energy=low_energy)
        violations = validate_schedule(plan.schedule, list(plan.tasks), plan.context)
        if violations:
            failures.append(f"sweep day {index}: {violations[0].code.value}")
            continue
        if plan.mode is PlanMode.MINIMUM:
            minimum_days += 1
            accounted = {t.key for t in plan.tasks} | {d.task_key for d in plan.dropped}
            if len(plan.tasks) > 2 or accounted != {t.key for t in tasks}:
                failures.append(f"sweep day {index}: minimum day broke its own rules")
        elif low_energy:
            failures.append(f"sweep day {index}: low-energy day was not a minimum day")
    return SWEEP_DAYS, minimum_days, failures


@dataclass(frozen=True)
class EvalResult:
    golden_total: int
    golden_ok: int
    tamper_caught: int
    tamper_total: int
    sweep_days: int
    sweep_minimum_days: int
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


def run() -> EvalResult:
    golden_failures = _check_golden()
    caught, tamper_total, tamper_failures = _check_tampering()
    days, minimum_days, sweep_failures = _check_sweep()
    total = len(_golden_cases())
    return EvalResult(
        golden_total=total,
        golden_ok=total - len(golden_failures),
        tamper_caught=caught,
        tamper_total=tamper_total,
        sweep_days=days,
        sweep_minimum_days=minimum_days,
        failures=tuple([*golden_failures, *tamper_failures, *sweep_failures]),
    )


def main() -> int:
    result = run()
    print("Planning eval")
    print(f"  golden days correct   : {result.golden_ok}/{result.golden_total}")
    print(f"  tampering caught      : {result.tamper_caught}/{result.tamper_total}")
    print(
        f"  random sweep          : {result.sweep_days} days, "
        f"{result.sweep_minimum_days} fell back to a minimum day, all valid"
        if result.passed
        else f"  random sweep          : {result.sweep_days} days"
    )
    print("Known gaps (not in the gate):")
    for gap in KNOWN_GAPS:
        print(f"  {gap}")
    for failure in result.failures[:10]:
        print(f"  FAIL {failure}")
    print("RESULT: PASS" if result.passed else "RESULT: FAIL")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
