"""Embed the methodology library into Postgres (pgvector).

    python -m app.retrieval.index

Safe to re-run: only methods whose text changed are re-embedded.
"""

from app.db.session import get_sessionmaker
from app.methods.loader import get_library
from app.retrieval.embedder import get_embedder
from app.retrieval.retriever import index_methods
from app.retrieval.store import PgVectorStore


def main() -> int:
    embedder = get_embedder()
    with get_sessionmaker()() as db:
        result = index_methods(list(get_library()), embedder, PgVectorStore(db, embedder.dim))
    print(
        f"Indexed with {embedder.name}: added {result.added}, updated {result.updated}, "
        f"unchanged {result.unchanged}, removed {result.removed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
