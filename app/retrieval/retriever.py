import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

from app.methods.loader import get_library
from app.methods.schema import EvidenceLevel, Method
from app.methods.taxonomy import RoadblockType
from app.retrieval.embedder import Embedder
from app.retrieval.store import VectorStore

_EVIDENCE_RANK = {
    EvidenceLevel.STRONG: 3,
    EvidenceLevel.MODERATE: 2,
    EvidenceLevel.LIMITED: 1,
    EvidenceLevel.PRACTITIONER: 0,
}


class RetrievalIndexError(Exception):
    """The index is missing methods that the library has. Re-run the indexer."""


@dataclass(frozen=True)
class IndexResult:
    added: int
    updated: int
    unchanged: int
    removed: int


@dataclass(frozen=True)
class Retrieved:
    slug: str
    similarity: float
    matched: tuple[RoadblockType, ...]


def method_document(method: Method) -> str:
    """The text that represents a method for search."""
    parts = [
        method.title,
        method.summary,
        method.target_behavior,
        method.ideal_context,
        *method.steps,
    ]
    return " ".join(parts)


def content_hash(embedder: Embedder, method: Method) -> str:
    payload = f"{embedder.name}\n{method_document(method)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def index_methods(methods: Sequence[Method], embedder: Embedder, store: VectorStore) -> IndexResult:
    """Bring the store in line with the library. Only changed methods are re-embedded."""
    existing = store.get_hashes()
    wanted = {m.slug: content_hash(embedder, m) for m in methods}
    changed = [m for m in methods if existing.get(m.slug) != wanted[m.slug]]
    vectors = embedder.embed([method_document(m) for m in changed]) if changed else []
    added = updated = 0
    for method, vector in zip(changed, vectors, strict=True):
        if method.slug in existing:
            updated += 1
        else:
            added += 1
        store.upsert(method.slug, wanted[method.slug], embedder.name, vector)
    stale = [slug for slug in existing if slug not in wanted]
    if stale:
        store.delete(stale)
    return IndexResult(
        added=added, updated=updated, unchanged=len(methods) - len(changed), removed=len(stale)
    )


def retrieve_methods(
    *,
    roadblocks: Sequence[RoadblockType],
    situation: str,
    embedder: Embedder,
    store: VectorStore,
    library: Sequence[Method] | None = None,
    k: int = 3,
) -> list[Retrieved]:
    """Filter by roadblock first, then order by how many roadblocks match, then similarity.

    Ties on both fall back to stronger evidence, then the slug, so results are deterministic.
    """
    if k < 1:
        raise ValueError("k must be at least 1")
    methods = list(get_library() if library is None else library)
    wanted = set(roadblocks)

    candidates: list[tuple[Method, tuple[RoadblockType, ...]]] = []
    for method in methods:
        hits = tuple(r for r in method.targets if r in wanted)
        if hits:
            candidates.append((method, hits))
    if not candidates:
        return []

    slugs = [method.slug for method, _ in candidates]
    similarities: dict[str, float] = {}
    if situation.strip():
        query = embedder.embed([situation])[0]
        if any(query):  # an all-zero query (only stop words) cannot be compared
            similarities = store.search(query, slugs, len(slugs))
            missing = set(slugs) - set(similarities)
            if missing:
                raise RetrievalIndexError(f"not indexed: {', '.join(sorted(missing))}")

    ranked = sorted(
        candidates,
        key=lambda c: (
            -len(c[1]),
            -similarities.get(c[0].slug, 0.0),
            -_EVIDENCE_RANK[c[0].evidence_level],
            c[0].slug,
        ),
    )
    return [
        Retrieved(slug=m.slug, similarity=similarities.get(m.slug, 0.0), matched=hits)
        for m, hits in ranked[:k]
    ]
