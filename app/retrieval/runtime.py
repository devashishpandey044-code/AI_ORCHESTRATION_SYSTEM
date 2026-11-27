from dataclasses import dataclass
from functools import lru_cache

from app.methods.loader import get_library
from app.methods.schema import Method
from app.retrieval.embedder import Embedder, get_embedder
from app.retrieval.retriever import index_methods
from app.retrieval.store import InMemoryVectorStore, VectorStore


@dataclass(frozen=True)
class RetrievalIndex:
    embedder: Embedder
    store: VectorStore
    library: tuple[Method, ...]


@lru_cache
def get_index() -> RetrievalIndex:
    """An in-memory index of the library, built once per process. The library is small."""
    library = tuple(get_library())
    embedder = get_embedder()
    store = InMemoryVectorStore()
    index_methods(library, embedder, store)
    return RetrievalIndex(embedder=embedder, store=store, library=library)
