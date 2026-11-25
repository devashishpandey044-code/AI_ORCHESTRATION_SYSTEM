"""Local, deterministic text embedder. No network, no cost, no model download.

Hashing-trick bag of words: lexical, not semantic. Good enough to build and test retrieval,
and replaceable behind the Embedder protocol by a real embedding model later.
"""

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    """
    a an the and or of to in on at for with without is are was were be been it this that these
    those you your i my me we our they them their as by from into than then so but not no if when
    while after before during over under up down out about can could should would will just also
    more most such very each every one two three do does did have has had get gets got am
    """.split()
)


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _stem(token: str) -> str:
    for suffix in ("ing", "ed", "s"):
        if len(token) > len(suffix) + 2 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def tokenize(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]


class HashingEmbedder:
    def __init__(self, dim: int = 256) -> None:
        self.dim = dim
        self.name = f"hashing-v1-{dim}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for token in tokenize(text):
            value = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")
            vector[value % self.dim] += 1.0 if (value >> 63) & 1 else -1.0
        norm = math.sqrt(sum(x * x for x in vector))
        return [x / norm for x in vector] if norm else vector


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity for unit-length vectors."""
    return sum(x * y for x, y in zip(a, b, strict=True))


def get_embedder() -> HashingEmbedder:
    return HashingEmbedder()
