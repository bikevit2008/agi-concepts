"""Provenance tracking — verifies LLM "recalled" memories against the store.

Strategy (V3 quorum, retrieval-first):
1. Compute embedding for the LLM-produced "recalled memory" text.
2. Compare against embeddings of every stored memory.
3. Classify by max similarity:
       sim ≥ real_threshold        → REAL          (truly recalled)
       uncertain_threshold ≤ sim   → UNCERTAIN     (similar but not 1:1)
       sim < uncertain_threshold   → HALLUCINATED  (no real basis)
       no stored memories at all    → HALLUCINATED  (always — Bug #4)

This is a CHEAP heuristic. It catches the obvious case (LLM fabricated
a memory when the store is empty) and the medium case (LLM mixed up
two memories). It can't catch sophisticated paraphrasing, but combined
with retrieval-first prompts (only inject REAL stored memories into the
LLM's context) the defense-in-depth is sufficient.
"""

from __future__ import annotations

import math
from typing import List, Tuple

import structlog

from src.contracts.memory import (
    MemoryEntry,
    ProvenanceVerdict,
)
from src.persistence.embedder import IEmbedder

logger = structlog.get_logger("consciousness.persistence.provenance")


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class EmbeddingProvenanceTracker:
    """Cosine-similarity provenance check.

    Args:
        embedder: any IEmbedder (the same one used for the store, ideally).
        real_threshold: similarity ≥ this → REAL.
        uncertain_threshold: similarity ≥ this and < real → UNCERTAIN.
    """

    def __init__(
        self,
        embedder: IEmbedder,
        real_threshold: float = 0.85,
        uncertain_threshold: float = 0.65,
    ) -> None:
        if real_threshold <= uncertain_threshold:
            raise ValueError(
                "real_threshold must be > uncertain_threshold "
                f"(got {real_threshold} <= {uncertain_threshold})"
            )
        self._embedder = embedder
        self._real_threshold = real_threshold
        self._uncertain_threshold = uncertain_threshold

    def verify_recall(
        self,
        recalled_text: str,
        stored_memories: List[MemoryEntry],
    ) -> ProvenanceVerdict:
        if not stored_memories:
            return ProvenanceVerdict.NO_STORE
        if not recalled_text or not recalled_text.strip():
            return ProvenanceVerdict.HALLUCINATED

        recalled_vec = self._embedder.embed(recalled_text)
        max_sim = 0.0
        for mem in stored_memories:
            if mem.embedding is None:
                # Compute on the fly if missing
                mem.embedding = self._embedder.embed(mem.content)
            sim = _cosine(recalled_vec, mem.embedding)
            if sim > max_sim:
                max_sim = sim

        if max_sim >= self._real_threshold:
            return ProvenanceVerdict.REAL
        if max_sim >= self._uncertain_threshold:
            return ProvenanceVerdict.UNCERTAIN
        return ProvenanceVerdict.HALLUCINATED

    def filter_recalls(
        self,
        recalled_texts: List[str],
        stored_memories: List[MemoryEntry],
    ) -> List[Tuple[str, ProvenanceVerdict]]:
        return [(t, self.verify_recall(t, stored_memories)) for t in recalled_texts]


__all__ = ["EmbeddingProvenanceTracker"]
