"""Check that retrieval puts the expected method in the top results.

    python -m app.evals.retrieval

Gate: the expected method must be in the top 3 for every case. Rank 1 is reported but is not
gated, because word-based matching is weak and the library keeps growing.
"""

from dataclasses import dataclass, field

from app.evals.retrieval_cases import CASES, RetrievalCase
from app.methods.loader import get_library
from app.retrieval.embedder import get_embedder
from app.retrieval.retriever import index_methods, retrieve_methods
from app.retrieval.store import InMemoryVectorStore


@dataclass
class RetrievalReport:
    embedder: str = ""
    methods: int = 0
    total: int = 0
    top3: int = 0
    top1: int = 0
    misses: list[str] = field(default_factory=list)
    top1_misses: list[str] = field(default_factory=list)


def run_retrieval_eval(cases: list[RetrievalCase] | None = None) -> RetrievalReport:
    library = list(get_library())
    embedder = get_embedder()
    store = InMemoryVectorStore()
    index_methods(library, embedder, store)
    report = RetrievalReport(embedder=embedder.name, methods=len(library))
    for case in CASES if cases is None else cases:
        results = retrieve_methods(
            roadblocks=case.roadblocks,
            situation=case.situation,
            embedder=embedder,
            store=store,
            library=library,
            k=3,
        )
        slugs = [r.slug for r in results]
        report.total += 1
        if case.expected_slug in slugs:
            report.top3 += 1
        else:
            report.misses.append(f"{case.id}: expected {case.expected_slug}, got {slugs}")
        if slugs[:1] == [case.expected_slug]:
            report.top1 += 1
        else:
            first = slugs[0] if slugs else "nothing"
            report.top1_misses.append(
                f"{case.id}: expected {case.expected_slug}, first was {first}"
            )
    return report


def main() -> int:
    report = run_retrieval_eval()
    print(f"Retrieval eval ({report.embedder}, library of {report.methods} methods)")
    print(f"  expected method in top 3  : {report.top3}/{report.total}")
    print(f"  expected method ranked 1st: {report.top1}/{report.total}  (informational)")
    for line in report.misses:
        print("  MISS:", line)
    for line in report.top1_misses:
        print("  not first:", line)
    passed = report.top3 == report.total
    print("RESULT:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
