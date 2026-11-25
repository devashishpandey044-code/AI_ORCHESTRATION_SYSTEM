"""Check the roadblock rules and the verification of model output against golden cases.

    python -m app.evals.roadblocks

Exit code 0 = every case behaved as labelled. CI runs this on every push.
"""

from dataclasses import dataclass, field

from app.evals.roadblocks_cases import RULE_CASES, VERIFY_CASES, RuleCase, VerifyCase
from app.roadblocks.detector import RoadblockProposal, merge, verify_proposal
from app.roadblocks.rules import detect_from_execution
from app.schemas.roadblocks import ExecutionSummary


@dataclass
class RoadblockEvalReport:
    rule_total: int = 0
    rule_ok: int = 0
    verify_total: int = 0
    verify_ok: int = 0
    failures: list[str] = field(default_factory=list)


def _rule_case_ok(case: RuleCase) -> bool:
    data = ExecutionSummary.model_validate(case.execution)
    found = {d.roadblock for d in detect_from_execution(data)[0]}
    return found == set(case.expected)


def _verify_case_ok(case: VerifyCase) -> bool:
    proposal = RoadblockProposal.model_validate(case.model_output)
    found, dropped = verify_proposal(proposal, case.user_text)
    got = {d.roadblock: d.strength.value for d in merge([], found)}
    return got == case.expected and tuple(dropped) == case.dropped


def run_roadblock_eval() -> RoadblockEvalReport:
    report = RoadblockEvalReport()
    for rule_case in RULE_CASES:
        report.rule_total += 1
        if _rule_case_ok(rule_case):
            report.rule_ok += 1
        else:
            report.failures.append(f"rule case failed: {rule_case.id}")
    for verify_case in VERIFY_CASES:
        report.verify_total += 1
        if _verify_case_ok(verify_case):
            report.verify_ok += 1
        else:
            report.failures.append(f"verification case failed: {verify_case.id}")
    return report


def main() -> int:
    report = run_roadblock_eval()
    print("Roadblock eval")
    print(f"  rule cases correct        : {report.rule_ok}/{report.rule_total}")
    print(f"  verification cases correct: {report.verify_ok}/{report.verify_total}")
    for line in report.failures:
        print("  FAIL:", line)
    passed = not report.failures
    print("RESULT:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
