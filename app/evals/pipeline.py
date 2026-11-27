"""Run the whole Week 3 pipeline on golden cases and check the rules that must always hold.

    python -m app.evals.pipeline

Exit code 0 = every case behaved as labelled and every invariant held. CI runs this.
"""

import itertools
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import models  # noqa: F401  (registers the tables)
from app.db.base import Base
from app.evals.pipeline_cases import CASES, PipelineCase
from app.llm.base import LLMProviderError
from app.llm.fake import FakeProvider
from app.methods.loader import get_library
from app.methods.taxonomy import SENSITIVE, RoadblockType
from app.retrieval.runtime import get_index
from app.roadblocks.detector import detect_roadblocks
from app.safety.crisis import check_text
from app.schemas.methods import SuggestResponse
from app.schemas.roadblocks import ExecutionSummary
from app.services.methods import MAX_SUGGESTIONS, suggest_methods

SWEEP_SITUATIONS = ("", "I feel overwhelmed and I cannot focus")


class _BrokenProvider:
    name = "broken"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete(self, *, system: str, user: str, max_tokens: int = 1024):
        self.calls.append(user)
        raise LLMProviderError("Anthropic returned HTTP 500")


def _provider(case: PipelineCase):
    if case.model_fails:
        return _BrokenProvider()
    answer = case.model_output if case.model_output is not None else {"roadblocks": []}
    return FakeProvider([json.dumps(answer)])


def check_invariants(requested: Sequence[RoadblockType], response: SuggestResponse) -> list[str]:
    """Rules that must hold for every suggestion response, whatever the input."""
    problems: list[str] = []
    known = {m.slug for m in get_library()}
    slugs = [s.slug for s in response.suggestions]
    if len(slugs) > MAX_SUGGESTIONS:
        problems.append(f"{len(slugs)} suggestions, the limit is {MAX_SUGGESTIONS}")
    if len(slugs) != len(set(slugs)):
        problems.append("the same method was suggested twice")
    for s in response.suggestions:
        if s.slug not in known:
            problems.append(f"{s.slug} is not in the library")
        if not set(s.matched_roadblocks) <= set(requested):
            problems.append(f"{s.slug} claims a roadblock that was not requested")
        if not s.reasons:
            problems.append(f"{s.slug} has no reasons")
        if not s.contraindications:
            problems.append(f"{s.slug} has no contraindications")
        if set(s.targets) & SENSITIVE and not s.escalation_note:
            problems.append(f"{s.slug} targets energy or burnout but has no escalation note")
    sensitive_chosen = any(set(s.targets) & SENSITIVE for s in response.suggestions)
    if sensitive_chosen != (response.care_note is not None):
        problems.append("the care note is missing or present at the wrong time")
    return problems


def run_case(case: PipelineCase, db: Session) -> list[str]:
    problems: list[str] = []
    provider = _provider(case)
    user_id = uuid.uuid4()

    # 1. Safety comes first, exactly as in the routes. A trigger stops everything.
    safety_hit = bool(case.text and check_text(case.text).triggered)
    if safety_hit != case.expect_safety:
        problems.append(f"safety expected {case.expect_safety}, got {safety_hit}")
    if safety_hit:
        if provider.calls:
            problems.append("the model was called after a crisis was detected")
        return problems

    # 2. Detect roadblocks.
    execution = ExecutionSummary.model_validate(case.execution) if case.execution else None
    result = detect_roadblocks(db, provider, user_id, case.text, execution)
    got = {d.roadblock: d.strength.value for d in result.roadblocks}
    if got != case.expect_roadblocks:
        problems.append(f"roadblocks expected {_show(case.expect_roadblocks)}, got {_show(got)}")
    if (result.care_note is not None) != case.expect_detection_care_note:
        problems.append("the detection care note is missing or present at the wrong time")
    for needle in case.expect_note_contains:
        if not any(needle in note for note in result.notes):
            problems.append(f"expected a note mentioning '{needle}'")
    if case.expect_model_calls is not None and len(provider.calls) != case.expect_model_calls:
        problems.append(
            f"expected {case.expect_model_calls} model calls, got {len(provider.calls)}"
        )

    # 3. Suggest methods for what was detected (the user accepts all of it, at most four).
    accepted = [d.roadblock for d in result.roadblocks][:4]
    if not accepted:
        if case.expect_methods_in_top2:
            problems.append("expected suggestions but no roadblock was detected")
        return problems
    response = suggest_methods(db, user_id, get_index(), accepted, (case.text or "").strip())
    slugs = [s.slug for s in response.suggestions]
    for slug in case.expect_methods_in_top2:
        if slug not in slugs:
            problems.append(f"expected {slug} among the suggestions, got {slugs}")
    problems.extend(check_invariants(accepted, response))
    return problems


def _show(mapping: dict) -> dict[str, str]:
    return {key.value: value for key, value in mapping.items()}


def sweep_combinations(db: Session) -> tuple[int, int, list[str]]:
    """Ask for methods for every combination of 1 to 4 roadblocks.

    Returns (combinations, requests, problems).
    """
    index = get_index()
    problems: list[str] = []
    combos = requests = 0
    for size in range(1, 5):
        for combo in itertools.combinations(list(RoadblockType), size):
            combos += 1
            for situation in SWEEP_SITUATIONS:
                requests += 1
                response = suggest_methods(db, uuid.uuid4(), index, combo, situation)
                label = ",".join(r.value for r in combo)
                if not response.suggestions:
                    problems.append(f"[{label}] no suggestion at all")
                problems.extend(f"[{label}] {p}" for p in check_invariants(combo, response))
    return combos, requests, problems


@dataclass
class PipelineReport:
    total: int = 0
    ok: int = 0
    combos: int = 0
    requests: int = 0
    failures: list[str] = field(default_factory=list)


def run_pipeline_eval(cases: list[PipelineCase] | None = None) -> PipelineReport:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    report = PipelineReport()
    with sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)() as db:
        for case in CASES if cases is None else cases:
            report.total += 1
            problems = run_case(case, db)
            if problems:
                report.failures.extend(f"{case.id}: {p}" for p in problems)
            else:
                report.ok += 1
        report.combos, report.requests, sweep_problems = sweep_combinations(db)
        report.failures.extend(f"sweep {p}" for p in sweep_problems)
    engine.dispose()
    return report


def main() -> int:
    report = run_pipeline_eval()
    print("Pipeline eval")
    print(f"  golden cases correct : {report.ok}/{report.total}")
    print(
        f"  invariant sweep      : {report.requests} requests over {report.combos} "
        "roadblock combinations"
    )
    for line in report.failures[:20]:
        print("  FAIL:", line)
    if len(report.failures) > 20:
        print(f"  ... and {len(report.failures) - 20} more")
    passed = not report.failures
    print("RESULT:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
