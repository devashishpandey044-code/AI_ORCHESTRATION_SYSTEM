import math

import pytest

from app.methods.loader import get_library
from app.methods.schema import Method
from app.methods.taxonomy import RoadblockType as R
from app.retrieval.embedder import HashingEmbedder, dot
from app.retrieval.retriever import (
    RetrievalIndexError,
    index_methods,
    retrieve_methods,
)
from app.retrieval.store import InMemoryVectorStore


def make_method(slug, targets, words="general technique for everyday work", evidence="practitioner"):
    sources = ["Test, T. (2020). A fixture source. Journal, 1(1), 1-2."]
    return Method.model_validate(
        {
            "slug": slug,
            "title": slug.replace("_", " ").title(),
            "summary": f"This method is about {words}.",
            "targets": [t.value for t in targets],
            "target_behavior": f"Practise {words}.",
            "difficulty": "easy",
            "duration_minutes": 10,
            "schedule_kind": "daily_block",
            "steps": [
                f"First step about {words}.",
                f"Second step about {words}.",
                f"Third step about {words}.",
            ],
            "ideal_context": f"Useful when {words} matters.",
            "contraindications": ["Not for every situation."],
            "measurement": "Count the number of completed sessions.",
            "evidence_level": evidence,
            "evidence_note": "Test fixture with an invented evidence note.",
            "sources": sources if evidence in ("strong", "moderate") else [],
            "escalation_note": "Please talk to a doctor if this lasts.",
        }
    )


def build(methods):
    embedder = HashingEmbedder()
    store = InMemoryVectorStore()
    index_methods(methods, embedder, store)
    return embedder, store


# ---- embedder --------------------------------------------------------------

def test_embedding_is_deterministic_and_normalized():
    embedder = HashingEmbedder()
    first = embedder.embed(["Phone focus block"])[0]
    second = embedder.embed(["Phone focus block"])[0]
    assert first == second
    assert math.isclose(sum(x * x for x in first), 1.0, rel_tol=1e-9)


def test_blank_and_stopword_only_text_gives_zero_vector():
    embedder = HashingEmbedder()
    assert not any(embedder.embed([""])[0])
    assert not any(embedder.embed(["the and of to"])[0])


def test_related_text_scores_higher_than_unrelated():
    embedder = HashingEmbedder()
    query, phone_doc, memory_doc = embedder.embed(
        [
            "my phone notifications keep interrupting me",
            "keep the phone away so notifications stop interrupting focus",
            "recall flashcards to strengthen memory before the exam",
        ]
    )
    assert dot(query, phone_doc) > dot(query, memory_doc)


def test_embedding_dimension_and_name():
    assert len(HashingEmbedder().embed(["phone"])[0]) == 256
    assert HashingEmbedder().name == "hashing-v1-256"
    assert HashingEmbedder(dim=64).name == "hashing-v1-64"


def test_embed_many_preserves_order():
    embedder = HashingEmbedder()
    both = embedder.embed(["phone focus", "memory recall"])
    assert both == [embedder.embed(["phone focus"])[0], embedder.embed(["memory recall"])[0]]


# ---- in-memory store -------------------------------------------------------

def test_in_memory_store_upsert_search_delete():
    store = InMemoryVectorStore()
    embedder = HashingEmbedder()
    v1, v2 = embedder.embed(["phone focus", "memory recall"])
    store.upsert("a", "h1", "m", v1)
    store.upsert("b", "h2", "m", v2)
    assert store.get_hashes() == {"a": "h1", "b": "h2"}
    scores = store.search(embedder.embed(["phone"])[0], ["a", "b"], 2)
    assert scores["a"] > scores["b"]
    store.delete(["a"])
    assert store.get_hashes() == {"b": "h2"}


def test_search_respects_allowed_and_k():
    store = InMemoryVectorStore()
    embedder = HashingEmbedder()
    v1, v2 = embedder.embed(["phone focus", "memory recall"])
    store.upsert("a", "h1", "m", v1)
    store.upsert("b", "h2", "m", v2)
    query = embedder.embed(["phone"])[0]
    assert set(store.search(query, ["b"], 5)) == {"b"}
    assert list(store.search(query, ["a", "b"], 1)) == ["a"]


# ---- indexing --------------------------------------------------------------

def test_index_adds_then_is_idempotent():
    library = [make_method("aaa_method", [R.DISTRACTION]), make_method("bbb_method", [R.AVOIDANCE])]
    embedder, store = HashingEmbedder(), InMemoryVectorStore()
    first = index_methods(library, embedder, store)
    assert (first.added, first.updated, first.unchanged, first.removed) == (2, 0, 0, 0)
    second = index_methods(library, embedder, store)
    assert (second.added, second.updated, second.unchanged, second.removed) == (0, 0, 2, 0)


def test_index_updates_changed_content_and_removes_deleted():
    library = [make_method("aaa_method", [R.DISTRACTION]), make_method("bbb_method", [R.AVOIDANCE])]
    embedder, store = HashingEmbedder(), InMemoryVectorStore()
    index_methods(library, embedder, store)
    changed = [make_method("aaa_method", [R.DISTRACTION], words="something completely different")]
    result = index_methods(changed, embedder, store)
    assert (result.added, result.updated, result.unchanged, result.removed) == (0, 1, 0, 1)
    assert set(store.get_hashes()) == {"aaa_method"}


# ---- retrieval -------------------------------------------------------------

def test_retrieval_only_returns_methods_for_the_given_roadblocks():
    library = [
        make_method("one_distract", [R.DISTRACTION]),
        make_method("two_avoid", [R.AVOIDANCE]),
        make_method("three_load", [R.OVERLOAD]),
    ]
    embedder, store = build(library)
    results = retrieve_methods(
        roadblocks=[R.DISTRACTION],
        situation="anything about work",
        embedder=embedder,
        store=store,
        library=library,
    )
    assert [r.slug for r in results] == ["one_distract"]


def test_methods_matching_more_roadblocks_rank_first():
    library = [
        make_method("one_match", [R.DISTRACTION], words="phone notifications"),
        make_method("two_match", [R.DISTRACTION, R.AVOIDANCE], words="memory flashcards"),
    ]
    embedder, store = build(library)
    results = retrieve_methods(
        roadblocks=[R.DISTRACTION, R.AVOIDANCE],
        situation="phone notifications keep interrupting me",
        embedder=embedder,
        store=store,
        library=library,
    )
    assert [r.slug for r in results] == ["two_match", "one_match"]
    assert len(results[0].matched) == 2


def test_similarity_ranks_within_the_same_match_count():
    library = [
        make_method("memory_method", [R.DISTRACTION], words="memory flashcards recall"),
        make_method("phone_method", [R.DISTRACTION], words="phone notifications interruptions"),
    ]
    embedder, store = build(library)

    def top(situation):
        return retrieve_methods(
            roadblocks=[R.DISTRACTION],
            situation=situation,
            embedder=embedder,
            store=store,
            library=library,
        )[0].slug

    assert top("my phone notifications interrupt me") == "phone_method"
    assert top("I forget what I study and need memory flashcards recall") == "memory_method"


def test_k_limits_results_and_must_be_positive():
    library = [make_method(f"method_{n}", [R.DISTRACTION]) for n in ("aaa", "bbb", "ccc", "ddd")]
    embedder, store = build(library)
    kwargs = dict(
        roadblocks=[R.DISTRACTION], situation="work", embedder=embedder, store=store, library=library
    )
    assert len(retrieve_methods(k=2, **kwargs)) == 2
    with pytest.raises(ValueError):
        retrieve_methods(k=0, **kwargs)


def test_no_roadblocks_or_no_matches_returns_empty():
    library = [make_method("one_distract", [R.DISTRACTION])]
    embedder, store = build(library)
    kwargs = dict(situation="work", embedder=embedder, store=store, library=library)
    assert retrieve_methods(roadblocks=[], **kwargs) == []
    assert retrieve_methods(roadblocks=[R.OVERLOAD], **kwargs) == []


def test_blank_situation_falls_back_to_evidence_then_slug():
    library = [
        make_method("zeta_weak", [R.DISTRACTION], evidence="practitioner"),
        make_method("beta_strong", [R.DISTRACTION], evidence="strong"),
        make_method("alpha_strong", [R.DISTRACTION], evidence="strong"),
    ]
    embedder, store = build(library)
    results = retrieve_methods(
        roadblocks=[R.DISTRACTION], situation="   ", embedder=embedder, store=store, library=library
    )
    assert [r.slug for r in results] == ["alpha_strong", "beta_strong", "zeta_weak"]
    assert all(r.similarity == 0.0 for r in results)


def test_missing_index_raises():
    library = [make_method("one_distract", [R.DISTRACTION])]
    with pytest.raises(RetrievalIndexError):
        retrieve_methods(
            roadblocks=[R.DISTRACTION],
            situation="phone buzzing",
            embedder=HashingEmbedder(),
            store=InMemoryVectorStore(),
            library=library,
        )


def test_real_library_retrieval_returns_known_slugs():
    library = list(get_library())
    embedder, store = build(library)
    results = retrieve_methods(
        roadblocks=[R.DISTRACTION],
        situation="my phone keeps buzzing while I study",
        embedder=embedder,
        store=store,
        library=library,
    )
    known = {m.slug for m in library}
    assert results
    assert all(r.slug in known for r in results)
    assert "phone_friction" in [r.slug for r in results]
