"""Run the labelled cases through the out-of-scope floor.

    python -m app.evals.scope

Exit code 0 = every gate case behaved as labelled. CI runs this on every push.

Both directions gate. A missed refusal lets a clinical disclosure be matched to a method;
an over-refusal tells someone with an ordinary productivity problem that the app cannot
help them. Neither is acceptable in a gate case.
"""

from dataclasses import dataclass, field

from app.evals.scope_cases import CASES, ScopeCase
from app.intake.scope import check_scope


def classify(case: ScopeCase) -> str:
    actual = check_scope(case.text).out_of_scope
    if case.expect_out_of_scope and not actual:
        return "missed"
    if not case.expect_out_of_scope and actual:
        return "over_refused"
    return "ok"


@dataclass
class ScopeReport:
    refused: int = 0
    missed: int = 0
    kept: int = 0
    over_refused: int = 0
    known_gaps: dict[str, str] = field(default_factory=dict)

    @property
    def recall(self) -> float:
        total = self.refused + self.missed
        return self.refused / total if total else 1.0


def run_scope_eval(cases: list[ScopeCase] | None = None) -> ScopeReport:
    report = ScopeReport()
    for case in CASES if cases is None else cases:
        outcome = classify(case)
        if case.known_gap_kind is not None:
            report.known_gaps[case.id] = outcome
        elif case.expect_out_of_scope:
            if outcome == "ok":
                report.refused += 1
            else:
                report.missed += 1
        elif outcome == "ok":
            report.kept += 1
        else:
            report.over_refused += 1
    return report


def main() -> int:
    report = run_scope_eval()
    out_total = report.refused + report.missed
    in_total = report.kept + report.over_refused
    print("Scope eval (gate cases)")
    print(f"  out of scope refused : {report.refused}/{out_total}  (recall {report.recall:.0%})")
    print(
        f"  in scope left alone  : {report.kept}/{in_total}  (over-refused {report.over_refused})"
    )
    print("Known gaps (not in the gate):")
    for case_id, outcome in report.known_gaps.items():
        print(f"  {case_id}: {outcome}")
    passed = report.missed == 0 and report.over_refused == 0
    print("RESULT:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
