"""Check-in eval: does the plan-versus-actual and weekly review logic stay correct?

Four parts: golden days and weeks with known answers, tampered stored rows that must be
rejected, and a random sweep that checks invariants over thousands of days and weeks.
Pure code, no database and no model call. Run with: python -m app.evals.checkins
"""

import random
from dataclasses import dataclass, field
from operator import attrgetter

from app.checkins.compare import DayReport, compare_day
from app.checkins.patterns import analyze
from app.checkins.records import (
    CheckinRows,
    OutcomeRow,
    StoredCheckinCorrupt,
    checkin_to_rows,
    rows_to_checkin,
)
from app.checkins.types import (
    BlockReason,
    Checkin,
    CheckinError,
    TaskOutcome,
    TaskStatus,
)
from app.checkins.weekly import (
    HIGH_ADHERENCE,
    HIGH_UNREPORTED,
    LOW_ADHERENCE,
    MIN_DAYS_FOR_REVIEW,
    OVER_ESTIMATE,
    SuggestionCode,
    review_week,
)

D, P, S = TaskStatus.DONE, TaskStatus.PARTIAL, TaskStatus.SKIPPED
SEED = 2026
SWEEP_DAYS = 2000
SWEEP_WEEKS = 500
MAX_FAILURES_SHOWN = 10

KNOWN_GAPS = {
    "no_trend": "a week is judged alone; getting better or worse over weeks is not compared",
    "self_reported": "the user picks the reason for a miss and nothing checks it",
    "untuned_thresholds": "the 60/85/125/30 percent cut-offs are first guesses",
    "no_time_of_day": "a miss is not linked to when in the day the task was planned",
}


def _outcome(key: str, status: TaskStatus, minutes: int, reason: BlockReason | None = None):
    return TaskOutcome(key, status, minutes, reason)


def _day(planned: dict[str, int], *outcomes: TaskOutcome) -> DayReport:
    return compare_day(planned, Checkin(tuple(outcomes)))


T, I_, M, E = (
    BlockReason.TOO_TIRED,
    BlockReason.INTERRUPTED,
    BlockReason.LOST_MOTIVATION,
    BlockReason.OTHER,
)
SC = SuggestionCode


def _golden_days():
    """(name, planned, outcomes, expected adherence, counted, overrun, unreported)."""
    return [
        ("all done", {"a": 30, "b": 60}, [_outcome("a", D, 30), _outcome("b", D, 60)],
         100, 90, 0, ()),
        ("partial", {"a": 60}, [_outcome("a", P, 20, I_)], 33, 20, 0, ()),
        ("skipped", {"a": 30}, [_outcome("a", S, 0, T)], 0, 0, 0, ()),
        ("overrun is capped", {"a": 30}, [_outcome("a", D, 50)], 100, 30, 20, ()),
        ("unreported task", {"a": 30, "b": 30}, [_outcome("a", D, 30)], 50, 30, 0, ("b",)),
        ("empty check-in", {"a": 30}, [], 0, 0, 0, ("a",)),
        ("empty plan", {}, [], None, 0, 0, ()),
        ("rounds half up", {"a": 80}, [_outcome("a", P, 10, E)], 13, 10, 0, ()),
        ("mixed day", {"a": 30, "b": 60, "c": 30},
         [_outcome("a", D, 30), _outcome("b", P, 20, I_), _outcome("c", S, 0, T)],
         42, 50, 0, ()),
    ]


def _repeat(report: DayReport, times: int) -> list[DayReport]:
    return [report] * times


def _golden_weeks():
    """(name, list of day reports, expected suggestion codes in order)."""
    plan_ab = {"a": 30, "b": 60}
    all_done = _day(plan_ab, _outcome("a", D, 30), _outcome("b", D, 60))
    tired = _day(plan_ab, _outcome("a", D, 30), _outcome("b", S, 0, T))
    interrupted = _day(plan_ab, _outcome("a", D, 30), _outcome("b", P, 40, I_))
    slow = _day({"a": 40}, _outcome("a", D, 60))
    silent = _day({"a": 30, "b": 30}, _outcome("a", D, 30))
    unmotivated = _day(plan_ab, _outcome("a", S, 0, M), _outcome("b", D, 60))
    return [
        ("no days", [], [SC.NEED_MORE_DATA]),
        ("two days is too few", _repeat(all_done, 2), [SC.NEED_MORE_DATA]),
        ("three good days", _repeat(all_done, 3), [SC.KEEP_GOING]),
        ("tiredness repeats", _repeat(tired, 3), [SC.PLAN_LESS, SC.PROTECT_ENERGY]),
        ("interruptions repeat", _repeat(interrupted, 3), [SC.ADD_BUFFER]),
        ("estimates too short", _repeat(slow, 3), [SC.LONGER_ESTIMATES, SC.KEEP_GOING]),
        ("many tasks unreported", _repeat(silent, 3), [SC.REPORT_MORE, SC.PLAN_LESS]),
        ("motivation repeats", _repeat(unmotivated, 3), [SC.SMALLER_STARTS]),
    ]


def _tampered_rows():
    ok = OutcomeRow("a", "done", 10, None)
    return [
        ("unknown status", CheckinRows(None, "", (OutcomeRow("a", "finished", 10, None),))),
        ("unknown reason", CheckinRows(None, "", (OutcomeRow("a", "partial", 10, "lazy"),))),
        ("done with zero minutes", CheckinRows(None, "", (OutcomeRow("a", "done", 0, None),))),
        ("skipped with minutes",
         CheckinRows(None, "", (OutcomeRow("a", "skipped", 5, "other"),))),
        ("skipped without reason",
         CheckinRows(None, "", (OutcomeRow("a", "skipped", 0, None),))),
        ("done with a reason", CheckinRows(None, "", (OutcomeRow("a", "done", 10, "other"),))),
        ("minutes above a day", CheckinRows(None, "", (OutcomeRow("a", "done", 5000, None),))),
        ("task reported twice", CheckinRows(None, "", (ok, ok))),
        ("energy out of range", CheckinRows(9, "", (ok,))),
        ("note too long", CheckinRows(None, "x" * 501, (ok,))),
    ]


def _random_day(rng: random.Random) -> tuple[dict[str, int], Checkin]:
    planned = {f"t{i}": rng.choice(range(10, 241, 10)) for i in range(rng.randint(0, 6))}
    outcomes = []
    for key in planned:
        if rng.random() < 0.15:
            continue  # not reported
        status = rng.choice(list(TaskStatus))
        if status is S:
            outcomes.append(_outcome(key, S, 0, rng.choice(list(BlockReason))))
        elif status is P:
            reason = rng.choice([None, *BlockReason])
            outcomes.append(_outcome(key, P, rng.randint(1, 200), reason))
        else:
            outcomes.append(_outcome(key, D, rng.randint(1, 300)))
    energy = rng.choice([None, 1, 2, 3, 4, 5])
    return planned, Checkin(tuple(outcomes), energy, "")


@dataclass
class EvalResult:
    golden_days: tuple[int, int] = (0, 0)
    golden_weeks: tuple[int, int] = (0, 0)
    tampering: tuple[int, int] = (0, 0)
    sweep_days: int = 0
    sweep_weeks: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            self.golden_days[0] == self.golden_days[1]
            and self.golden_weeks[0] == self.golden_weeks[1]
            and self.tampering[0] == self.tampering[1]
            and not self.failures
        )


def _check_day_invariants(planned, checkin, report, failures, label):
    def bad(message):
        failures.append(f"{label}: {message}")

    if report.adherence_percent is not None and not 0 <= report.adherence_percent <= 100:
        bad("adherence outside 0..100")
    if report.counted_minutes > report.planned_minutes:
        bad("counted more than planned")
    if report.planned_minutes != sum(planned.values()):
        bad("planned total wrong")
    if sum(r.counted_minutes for r in report.results) != report.counted_minutes:
        bad("counted total is not the sum of the tasks")
    if report.overrun_minutes < 0:
        bad("negative overrun")
    reported = {r.key for r in report.results}
    if reported | set(report.unreported) != set(planned) or reported & set(report.unreported):
        bad("reported and unreported tasks do not partition the plan")
    back = rows_to_checkin(checkin_to_rows(checkin))
    key = attrgetter("key")
    if sorted(back.outcomes, key=key) != sorted(checkin.outcomes, key=key):
        bad("storage round trip changed the outcomes")
    if back.energy != checkin.energy:
        bad("storage round trip changed energy")


def _check_week_invariants(reports, review, failures, label):
    def bad(message):
        failures.append(f"{label}: {message}")

    codes = [s.code for s in review.suggestions]
    order = list(SuggestionCode)
    if len(set(codes)) != len(codes) or codes != sorted(codes, key=order.index):
        bad("suggestions repeat or are out of order")
    patterns = review.patterns
    enough = len(reports) >= MIN_DAYS_FOR_REVIEW
    if not enough:
        if codes != [SC.NEED_MORE_DATA]:
            bad("too few days but other suggestions given")
        return
    if SC.NEED_MORE_DATA in codes:
        bad("enough days but asked for more data")
    adherence = review.adherence_percent
    if (SC.PLAN_LESS in codes) != (adherence is not None and adherence < LOW_ADHERENCE):
        bad("plan_less does not match the adherence rule")
    unreported = patterns.unreported_percent
    if (SC.REPORT_MORE in codes) != (unreported is not None and unreported >= HIGH_UNREPORTED):
        bad("report_more does not match the unreported rule")
    ratio = patterns.estimate_ratio_percent
    if ratio is not None and ratio >= OVER_ESTIMATE and SC.LONGER_ESTIMATES not in codes:
        bad("estimates far too short but no suggestion")
    if SC.KEEP_GOING in codes:
        if adherence is None or adherence < HIGH_ADHERENCE or patterns.roadblocks:
            bad("keep_going despite low adherence or a roadblock")
        if SC.REPORT_MORE in codes:
            bad("keep_going together with report_more")
    for roadblock in patterns.roadblocks:
        if roadblock.occurrences < 3 or roadblock.days_affected < 2:
            bad("roadblock below the repeat thresholds")
        if not 0 <= roadblock.share_percent <= 100:
            bad("share outside 0..100")
    lost = [r.minutes_lost for r in patterns.roadblocks]
    if lost != sorted(lost, reverse=True):
        bad("roadblocks not ranked by minutes lost")
    if review.planned_minutes != sum(r.planned_minutes for r in reports):
        bad("weekly planned total wrong")
    if review != review_week(reports):
        bad("review is not deterministic")
    if analyze(reports) != patterns:
        bad("patterns differ between calls")


def run() -> EvalResult:
    result = EvalResult()

    right = 0
    for name, planned, outcomes, adherence, counted, overrun, unreported in _golden_days():
        report = compare_day(planned, Checkin(tuple(outcomes)))
        got = (report.adherence_percent, report.counted_minutes, report.overrun_minutes,
               report.unreported)
        if got == (adherence, counted, overrun, unreported):
            right += 1
        else:
            result.failures.append(f"golden day '{name}': got {got}")
    result.golden_days = (right, len(_golden_days()))

    right = 0
    weeks = _golden_weeks()
    for name, reports, expected in weeks:
        got = [s.code for s in review_week(reports).suggestions]
        if got == expected:
            right += 1
        else:
            result.failures.append(f"golden week '{name}': got {[c.value for c in got]}")
    result.golden_weeks = (right, len(weeks))

    caught = 0
    tampered = _tampered_rows()
    for name, rows in tampered:
        try:
            rows_to_checkin(rows)
        except StoredCheckinCorrupt:
            caught += 1
        else:
            result.failures.append(f"tampering not caught: {name}")
    total = len(tampered) + 1
    try:
        compare_day({"a": 30}, Checkin((_outcome("zzz", D, 10),)))
    except CheckinError:
        caught += 1
    else:
        result.failures.append("tampering not caught: task that was not planned")
    result.tampering = (caught, total)

    rng = random.Random(SEED)
    for i in range(SWEEP_DAYS):
        planned, checkin = _random_day(rng)
        report = compare_day(planned, checkin)
        _check_day_invariants(planned, checkin, report, result.failures, f"day {i}")
    result.sweep_days = SWEEP_DAYS
    for i in range(SWEEP_WEEKS):
        reports = []
        for _ in range(rng.randint(0, 7)):
            planned, checkin = _random_day(rng)
            reports.append(compare_day(planned, checkin))
        _check_week_invariants(reports, review_week(reports), result.failures, f"week {i}")
    result.sweep_weeks = SWEEP_WEEKS
    return result


def main() -> int:
    result = run()
    print("Check-in eval")
    print(f"  golden days correct   : {result.golden_days[0]}/{result.golden_days[1]}")
    print(f"  golden weeks correct  : {result.golden_weeks[0]}/{result.golden_weeks[1]}")
    print(f"  tampering caught      : {result.tampering[0]}/{result.tampering[1]}")
    state = "no invariant broken" if not result.failures else f"{len(result.failures)} problems"
    sweep = f"{result.sweep_days} days, {result.sweep_weeks} weeks, {state}"
    print(f"  random sweep          : {sweep}")
    for line in result.failures[:MAX_FAILURES_SHOWN]:
        print(f"  FAIL {line}")
    print("Known gaps (not in the gate):")
    for name, text in KNOWN_GAPS.items():
        print(f"  {name}: {text}")
    print("RESULT: PASS" if result.passed else "RESULT: FAIL")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
