"""Try retrieval from the command line (in-memory index, no database needed).

    python -m app.retrieval.demo --roadblocks distraction avoidance --text "my phone keeps buzzing"
"""

import argparse

from app.methods.loader import get_library
from app.methods.taxonomy import RoadblockType
from app.retrieval.embedder import get_embedder
from app.retrieval.retriever import index_methods, retrieve_methods
from app.retrieval.store import InMemoryVectorStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retrieve methods for roadblocks")
    parser.add_argument(
        "--roadblocks", nargs="+", required=True, choices=[r.value for r in RoadblockType]
    )
    parser.add_argument("--text", default="")
    parser.add_argument("-k", type=int, default=3)
    args = parser.parse_args(argv)

    library = list(get_library())
    embedder = get_embedder()
    store = InMemoryVectorStore()
    index_methods(library, embedder, store)
    results = retrieve_methods(
        roadblocks=[RoadblockType(r) for r in args.roadblocks],
        situation=args.text,
        embedder=embedder,
        store=store,
        library=library,
        k=args.k,
    )
    by_slug = {m.slug: m for m in library}
    for rank, item in enumerate(results, 1):
        method = by_slug[item.slug]
        matched = ",".join(r.value for r in item.matched)
        print(
            f"{rank}. {method.title} [{method.slug}] matched={matched} "
            f"similarity={item.similarity:.2f} evidence={method.evidence_level.value}"
        )
    if not results:
        print("No matching methods.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
