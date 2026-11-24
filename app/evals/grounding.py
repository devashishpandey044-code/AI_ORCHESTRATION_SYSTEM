"""Run the golden cases through the grounding check and report quality numbers.

    python -m app.evals.grounding

Exit code 0 = every gate case behaved correctly. CI runs this on every push.
"""

from dataclasses import dataclass, field

from app.evals.grounding_cases import CASES, GoldenCase
from app.schemas.life_model import LifeModelData, Provenance
from app.services.onboarding import verify_proposal

FIELDS = ("vision", "values", "priorities", "resources", "concerns")


@dataclass(frozen=True)
class ItemOutcome:
    case_id: str
    text: str
    invented: bool
    downgraded: bool

    @property
    def kind(self) -> str:
        if self.invented and self.downgraded:
            return "caught"
        if self.invented:
            return "missed"
        if self.downgraded:
            return "false_downgrade"
        return "kept"


@dataclass
class GroundingReport:
    caught: int = 0
    missed: int = 0
    false_downgrades: int = 0
    kept: int = 0
    known_gaps: dict[str, list[str]] = field(default_factory=dict)

    @property
    def catch_rate(self) -> float:
        total = self.caught + self.missed
        return self.caught / total if total else 1.0

    @property
    def false_downgrade_rate(self) -> float:
        total = self.false_downgrades + self.kept
        return self.false_downgrades / total if total else 0.0


def evaluate_case(case: GoldenCase) -> list[ItemOutcome]:
    original = LifeModelData.model_validate(case.model_output)
    verified, _notes = verify_proposal(original, case.user_text)
    outcomes: list[ItemOutcome] = []
    for name in FIELDS:
        for before, after in zip(getattr(original, name), getattr(verified, name), strict=True):
            if before.provenance == Provenance.INFERRED:
                continue  # the model already called it a guess; nothing to check
            outcomes.append(
                ItemOutcome(
                    case_id=case.id,
                    text=before.text,
                    invented=before.text in case.invented,
                    downgraded=after.provenance == Provenance.INFERRED,
                )
            )
    return outcomes


def run_grounding_eval(cases: list[GoldenCase] | None = None) -> GroundingReport:
    report = GroundingReport()
    for case in CASES if cases is None else cases:
        outcomes = evaluate_case(case)
        if case.known_gap_kind is not None:
            report.known_gaps[case.id] = sorted({o.kind for o in outcomes})
            continue
        for outcome in outcomes:
            if outcome.kind == "caught":
                report.caught += 1
            elif outcome.kind == "missed":
                report.missed += 1
            elif outcome.kind == "false_downgrade":
                report.false_downgrades += 1
            else:
                report.kept += 1
    return report


def main() -> int:
    report = run_grounding_eval()
    invented_total = report.caught + report.missed
    grounded_total = report.kept + report.false_downgrades
    print("Grounding eval (gate cases)")
    print(f"  invented items caught : {report.caught}/{invented_total}"
          f"  (catch rate {report.catch_rate:.0%})")
    print(f"  grounded items kept   : {report.kept}/{grounded_total}"
          f"  (false downgrades {report.false_downgrade_rate:.0%})")
    print("Known gaps (not in the gate):")
    for case_id, kinds in report.known_gaps.items():
        print(f"  {case_id}: {', '.join(kinds)}")
    passed = report.missed == 0 and report.false_downgrades == 0
    print("RESULT:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
