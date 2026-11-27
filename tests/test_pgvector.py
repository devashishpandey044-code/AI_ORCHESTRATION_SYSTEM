"""Tests against a real Postgres with pgvector. Skipped unless TEST_POSTGRES_URL is set.

The database name must end with _test: the fixture wipes the public schema when it finishes.
"""

import os
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.methods.loader import get_library
from app.methods.taxonomy import RoadblockType as R
from app.retrieval.embedder import HashingEmbedder
from app.retrieval.retriever import index_methods, retrieve_methods
from app.retrieval.store import InMemoryVectorStore, PgVectorStore

URL = os.environ.get("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_POSTGRES_URL is not set")


@pytest.fixture(scope="module")
def pg_session():
    database = make_url(URL).database or ""
    assert database.endswith("_test"), "refusing to run: database name must end with _test"
    env = {**os.environ, "DATABASE_URL": URL}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env,
        check=True,
        capture_output=True,
    )
    engine = create_engine(URL)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


@pytest.fixture()
def store(pg_session):
    pg_session.execute(text("DELETE FROM method_embeddings"))
    pg_session.commit()
    return PgVectorStore(pg_session, dim=256)


def test_pg_store_roundtrip(store):
    embedder = HashingEmbedder()
    a, b = embedder.embed(["phone distraction focus", "memory recall exam"])
    store.upsert("a", "h1", embedder.name, a)
    store.upsert("b", "h2", embedder.name, b)
    assert store.get_hashes() == {"a": "h1", "b": "h2"}

    scores = store.search(embedder.embed(["phone focus"])[0], ["a", "b"], 2)
    assert scores["a"] > scores["b"]

    store.upsert("a", "h3", embedder.name, a)
    assert store.get_hashes()["a"] == "h3"

    store.delete(["a"])
    assert set(store.get_hashes()) == {"b"}


def test_pg_retrieval_matches_in_memory(store):
    library = list(get_library())
    embedder = HashingEmbedder()
    memory = InMemoryVectorStore()
    index_methods(library, embedder, memory)
    index_methods(library, embedder, store)

    for roadblocks, situation in (
        ([R.DISTRACTION], "my phone keeps buzzing while I study"),
        ([R.AVOIDANCE, R.UNCLEAR_NEXT_STEP], "the project feels huge and I cannot begin"),
    ):
        kwargs = dict(roadblocks=roadblocks, situation=situation, embedder=embedder, library=library)
        from_pg = {r.slug for r in retrieve_methods(store=store, **kwargs)}
        from_memory = {r.slug for r in retrieve_methods(store=memory, **kwargs)}
        assert from_pg == from_memory


def test_pg_store_rejects_wrong_dimension(store):
    with pytest.raises(ValueError):
        store.upsert("x", "h", "m", [0.1] * 10)
