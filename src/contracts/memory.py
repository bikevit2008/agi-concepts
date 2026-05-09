"""Memory contracts — retrieval-first store + provenance tracking.

Two distinct responsibilities:
1. IMemoryStore — semantic memory backed by a vector database. Stores
   embeddings + metadata; supports semantic search by similarity.
2. IProvenanceTracker — checks whether an LLM-produced "recalled memory"
   actually corresponds to something stored, by comparing embeddings.
   Marks each recalled memory with a verdict (real / hallucinated /
   uncertain) so downstream code can act accordingly.

Together these implement the "retrieval-first, no hallucination" principle
from the V3 quorum audit. The Memory agent NEVER recalls without first
hitting the store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


class ProvenanceVerdict(str, Enum):
    """Classification of a recalled memory's authenticity."""

    REAL = "real"  # high similarity to a stored memory
    UNCERTAIN = "uncertain"  # mid similarity (in grey zone)
    HALLUCINATED = "hallucinated"  # no stored memory passes similarity threshold
    NO_STORE = "no_store"  # nothing in the store yet


@dataclass
class MemoryEntry:
    """A persisted memory with metadata.

    Fields:
        id: store-assigned identifier (string for portability)
        content: the textual memory
        embedding: dense vector (shape depends on embedder)
        source: where it came from ("perception", "reflection", ...)
        timestamp_ms: when it was stored
        emotion_associations: tags like {"joy": 0.8, "calm": 0.3}
        confidence: how confident we are this is a real memory
        extra: arbitrary metadata for forward compatibility
    """

    id: str
    content: str
    embedding: Optional[List[float]] = None
    source: str = "unknown"
    timestamp_ms: int = 0
    emotion_associations: Dict[str, float] = field(default_factory=dict)
    confidence: float = 1.0
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RecalledMemory:
    """A memory returned from a retrieval query, with its similarity score."""

    entry: MemoryEntry
    similarity: float  # 0.0..1.0 (cosine, or whatever metric the backend used)
    verdict: ProvenanceVerdict = ProvenanceVerdict.UNCERTAIN


@runtime_checkable
class IMemoryStore(Protocol):
    """Vector-based semantic memory store.

    Implementations:
    - InMemoryMemoryStore (no embeddings, simple substring match) — for tests
    - LanceDbMemoryStore (real embeddings, real vector search) — for prod
    """

    def store(self, entry: MemoryEntry) -> str:
        """Persist a memory. Returns assigned id (may differ from entry.id)."""
        ...

    def retrieve(
        self,
        query: str,
        limit: int = 5,
        min_similarity: float = 0.0,
        emotion_filter: Optional[Dict[str, float]] = None,
    ) -> List[RecalledMemory]:
        """Semantic search. Returns ranked list of (entry, similarity)."""
        ...

    def count(self) -> int:
        """Return total number of stored memories."""
        ...

    def all_contents(self) -> List[str]:
        """Return all stored memory contents (for legacy fallback paths)."""
        ...

    def close(self) -> None:
        """Flush + close."""
        ...


@runtime_checkable
class IProvenanceTracker(Protocol):
    """Verifies whether LLM-produced recall actually exists in the store.

    Strategy: embed the recalled text, compare to stored embeddings, classify
    based on max similarity:
        sim >= high_threshold  → REAL
        low_threshold <= sim < high_threshold → UNCERTAIN
        sim < low_threshold    → HALLUCINATED
    """

    def verify_recall(
        self,
        recalled_text: str,
        stored_memories: List[MemoryEntry],
    ) -> ProvenanceVerdict:
        """Classify a recalled memory against the stored set."""
        ...

    def filter_recalls(
        self,
        recalled_texts: List[str],
        stored_memories: List[MemoryEntry],
    ) -> List[tuple]:
        """Bulk classify. Returns [(text, verdict), ...]."""
        ...


# ---------------------------------------------------------------------------
# Null implementations (Null Object Pattern)
# ---------------------------------------------------------------------------


class NullMemoryStore:
    """No-op memory store: stores in a Python list, no embeddings.

    Useful for tests and as a baseline. Provides O(n) substring search.
    """

    def __init__(self) -> None:
        self._entries: List[MemoryEntry] = []

    def store(self, entry: MemoryEntry) -> str:
        if not entry.id:
            entry.id = f"mem_{len(self._entries)}"
        self._entries.append(entry)
        return entry.id

    def retrieve(
        self,
        query: str,
        limit: int = 5,
        min_similarity: float = 0.0,
        emotion_filter: Optional[Dict[str, float]] = None,
    ) -> List[RecalledMemory]:
        # Naive substring match for tests; production uses LanceDB.
        q = query.lower()
        results: List[RecalledMemory] = []
        for entry in self._entries:
            content = entry.content.lower()
            if q and q in content:
                results.append(
                    RecalledMemory(entry=entry, similarity=1.0, verdict=ProvenanceVerdict.REAL)
                )
        return results[:limit]

    def count(self) -> int:
        return len(self._entries)

    def all_contents(self) -> List[str]:
        return [e.content for e in self._entries]

    def close(self) -> None:
        return None


class NullProvenanceTracker:
    """No-op provenance: marks recalls as REAL if anything is stored,
    HALLUCINATED if nothing is stored. Cheap pre-MVP signal."""

    def verify_recall(
        self,
        recalled_text: str,
        stored_memories: List[MemoryEntry],
    ) -> ProvenanceVerdict:
        if not stored_memories:
            return ProvenanceVerdict.HALLUCINATED
        return ProvenanceVerdict.UNCERTAIN

    def filter_recalls(
        self,
        recalled_texts: List[str],
        stored_memories: List[MemoryEntry],
    ) -> List[tuple]:
        verdict = self.verify_recall("", stored_memories)
        return [(t, verdict) for t in recalled_texts]
