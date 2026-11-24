from collections.abc import Sequence
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.retrieval.embedder import dot


class VectorStore(Protocol):
    def get_hashes(self) -> dict[str, str]: ...

    def upsert(self, slug: str, content_hash: str, model: str, vector: list[float]) -> None: ...

    def delete(self, slugs: Sequence[str]) -> None: ...

    def search(self, vector: list[float], allowed: Sequence[str], k: int) -> dict[str, float]:
        """Cosine similarity for the allowed slugs only, best first, at most k."""
        ...


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._rows: dict[str, tuple[str, list[float]]] = {}

    def get_hashes(self) -> dict[str, str]:
        return {slug: content_hash for slug, (content_hash, _) in self._rows.items()}

    def upsert(self, slug: str, content_hash: str, model: str, vector: list[float]) -> None:
        self._rows[slug] = (content_hash, list(vector))

    def delete(self, slugs: Sequence[str]) -> None:
        for slug in slugs:
            self._rows.pop(slug, None)

    def search(self, vector: list[float], allowed: Sequence[str], k: int) -> dict[str, float]:
        scores = {slug: dot(vector, self._rows[slug][1]) for slug in allowed if slug in self._rows}
        best = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:k]
        return dict(best)


def _to_pg(vector: Sequence[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in vector) + "]"


class PgVectorStore:
    """Stores method embeddings in Postgres with the pgvector extension.

    The table is created by a hand-written migration (see migrations/versions).
    """

    def __init__(self, db: Session, dim: int) -> None:
        self._db = db
        self._dim = dim

    def _check(self, vector: Sequence[float]) -> None:
        if len(vector) != self._dim:
            raise ValueError(f"expected a vector of {self._dim} numbers, got {len(vector)}")

    def get_hashes(self) -> dict[str, str]:
        rows = self._db.execute(text("SELECT slug, content_hash FROM method_embeddings"))
        return {row.slug: row.content_hash for row in rows}

    def upsert(self, slug: str, content_hash: str, model: str, vector: list[float]) -> None:
        self._check(vector)
        self._db.execute(
            text(
                """
                INSERT INTO method_embeddings (slug, content_hash, model, embedding, updated_at)
                VALUES (:slug, :content_hash, :model, CAST(:vec AS vector), now())
                ON CONFLICT (slug) DO UPDATE SET
                    content_hash = EXCLUDED.content_hash,
                    model = EXCLUDED.model,
                    embedding = EXCLUDED.embedding,
                    updated_at = now()
                """
            ),
            {"slug": slug, "content_hash": content_hash, "model": model, "vec": _to_pg(vector)},
        )
        self._db.commit()

    def delete(self, slugs: Sequence[str]) -> None:
        if not slugs:
            return
        self._db.execute(
            text("DELETE FROM method_embeddings WHERE slug = ANY(:slugs)"), {"slugs": list(slugs)}
        )
        self._db.commit()

    def search(self, vector: list[float], allowed: Sequence[str], k: int) -> dict[str, float]:
        self._check(vector)
        if not allowed:
            return {}
        rows = self._db.execute(
            text(
                """
                SELECT slug, 1 - (embedding <=> CAST(:vec AS vector)) AS score
                FROM method_embeddings
                WHERE slug = ANY(:slugs)
                ORDER BY embedding <=> CAST(:vec AS vector)
                LIMIT :k
                """
            ),
            {"vec": _to_pg(vector), "slugs": list(allowed), "k": k},
        )
        return {row.slug: float(row.score) for row in rows}
