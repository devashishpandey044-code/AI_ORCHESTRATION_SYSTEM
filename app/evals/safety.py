"""Run the labelled cases through the crisis check.

    python -m app.evals.safety

Exit code 0 = every gate case behaved as labelled. CI runs this on every push.
"""

from dataclasses import dataclass, field

from app.evals.safety_cases import CASES, SafetyCase
from app.safety.crisis import check_text


def classify(case: SafetyCase) -> str:
    actual = check_text(case.text).triggered
    if case.expect_trigger and not actual:
        return "missed"
    if not case.expect_trigger and actual:
        return "over_trigger"
    return "ok"


@dataclass
class SafetyReport:
    caught: int = 0
    missed: int = 0
    false_positives: int = 0
    clean: int = 0
    known_gaps: dict[str, str] = field(default_factory=dict)

    @property
    def recall(self) -> float:
        total = self.caught + self.missed
        return self.caught / total if total else 1.0


def run_safety_eval(cases: list[SafetyCase] | None = None) -> SafetyReport:
    report = SafetyReport()
    for case in CASES if cases is None else cases:
        outcome = classify(case)
        if case.known_gap_kind is not None:
            report.known_gaps[case.id] = outcome
        elif case.expect_trigger:
            if outcome == "ok":
                report.caught += 1
            else:
                report.missed += 1
        elif outcome == "ok":
            report.clean += 1
        else:
            report.false_positives += 1
    return report


def main() -> int:
    report = run_safety_eval()
    risk_total = report.caught + report.missed
    benign_total = report.clean + report.false_positives
    print("Safety eval (gate cases)")
    print(f"  risk statements caught  : {report.caught}/{risk_total}  (recall {report.recall:.0%})")
    print(f"  benign texts left alone : {report.clean}/{benign_total}"
          f"  (false positives {report.false_positives})")
    print("Known gaps (not in the gate):")
    for case_id, outcome in report.known_gaps.items():
        print(f"  {case_id}: {outcome}")
    passed = report.missed == 0 and report.false_positives == 0
    print("RESULT:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
