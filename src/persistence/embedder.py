"""Embedders — pluggable text → vector encoders.

Two implementations:

1. HashingEmbedder — deterministic, dependency-free. Uses MurmurHash-like
   hashing on word n-grams to populate a fixed-dimension vector. Decent
   for tests and fallbacks; not state-of-the-art on semantic similarity
   but good enough to discriminate near-duplicates.

2. SentenceTransformerEmbedder — production-grade, requires
   `sentence-transformers` + `torch`. Default model BAAI/bge-small-en-v1.5
   (384 dims, ~30MB, multilingual-friendly enough for our use case).

The `IEmbedder` protocol is intentionally small (just `embed`,
`dimension`) so swapping backends is trivial.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import List, Protocol, runtime_checkable

import structlog

logger = structlog.get_logger("consciousness.persistence.embedder")


@runtime_checkable
class IEmbedder(Protocol):
    @property
    def dimension(self) -> int: ...

    def embed(self, text: str) -> List[float]: ...

    def embed_batch(self, texts: List[str]) -> List[List[float]]: ...


# ---------------------------------------------------------------------------
# Hashing embedder (no external deps)
# ---------------------------------------------------------------------------


_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


class HashingEmbedder:
    """Hashing trick → fixed-dim vector. No ML deps required.

    Algorithm:
    1. Tokenize text by `\\w+` regex.
    2. Generate unigrams + bigrams.
    3. For each token, compute SHA1, fold into [0, dimension); the sign
       comes from a second hash (prevents systematic sign bias).
    4. L2-normalize the resulting vector.

    Properties:
    - Deterministic (cosine sim is stable across runs).
    - Two slightly different sentences (1 word changed) produce vectors
      with cosine ~0.7-0.95 — good enough to discriminate "real recall"
      from "completely fabricated".
    """

    def __init__(self, dimension: int = 256) -> None:
        if dimension < 16:
            raise ValueError("HashingEmbedder dimension must be >= 16")
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    @staticmethod
    def _h(token: str) -> int:
        return int.from_bytes(hashlib.sha1(token.encode("utf-8")).digest()[:8], "big")

    @staticmethod
    def _sign(token: str) -> int:
        return 1 if int.from_bytes(hashlib.md5(token.encode("utf-8")).digest()[:1], "big") % 2 == 0 else -1

    def embed(self, text: str) -> List[float]:
        if not text:
            return [0.0] * self._dimension

        tokens = _TOKEN_RE.findall(text.lower())
        # bigrams strengthen local context
        bigrams = [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
        all_features = tokens + bigrams

        vec = [0.0] * self._dimension
        for f in all_features:
            idx = self._h(f) % self._dimension
            vec[idx] += float(self._sign(f))

        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.embed(t) for t in texts]


# ---------------------------------------------------------------------------
# SentenceTransformer embedder (production)
# ---------------------------------------------------------------------------


class SentenceTransformerEmbedder:
    """Wraps a `sentence_transformers.SentenceTransformer` model.

    Default: BAAI/bge-small-en-v1.5 (384 dims). Multilingual-tolerant
    enough for the consciousness system's mostly-Russian content,
    though for pure-Russian deployments consider `cointegrated/rubert-tiny2`
    or `LaBSE`.

    Lazy-imports sentence_transformers so the rest of the persistence
    layer works on machines that haven't installed torch yet.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        device: str = "cpu",
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "sentence-transformers is not installed. Either install it "
                "(`pip install sentence-transformers`) or use HashingEmbedder."
            ) from e

        logger.info("loading_sentence_transformer", model=model_name, device=device)
        self._model = SentenceTransformer(model_name, device=device)
        # Newer ST renamed `get_sentence_embedding_dimension` →
        # `get_embedding_dimension`. Use whichever exists.
        if hasattr(self._model, "get_embedding_dimension"):
            self._dimension = int(self._model.get_embedding_dimension())
        else:
            self._dimension = int(self._model.get_sentence_embedding_dimension())
        self._model_name = model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, text: str) -> List[float]:
        if not text:
            return [0.0] * self._dimension
        vec = self._model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        return [float(x) for x in vec.tolist()]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        vecs = self._model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return [[float(x) for x in v.tolist()] for v in vecs]


__all__ = ["IEmbedder", "HashingEmbedder", "SentenceTransformerEmbedder"]
