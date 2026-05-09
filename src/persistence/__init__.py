"""Persistence subsystem — event sourcing + checkpoint + memory store + provenance.

Backed by SQLite WAL for events/checkpoints (Stage 4) and LanceDB for
vector memories (Stage 5). Both have lighter fallback implementations
that are always available.
"""

from src.persistence.embedder import (
    HashingEmbedder,
    IEmbedder,
    SentenceTransformerEmbedder,
)
from src.persistence.memory_store import InMemoryMemoryStore, LanceDbMemoryStore
from src.persistence.provenance import EmbeddingProvenanceTracker
from src.persistence.sqlite_checkpoint import SqliteCheckpoint
from src.persistence.sqlite_event_store import SqliteEventStore

__all__ = [
    # Stage 4
    "SqliteCheckpoint",
    "SqliteEventStore",
    # Stage 5
    "HashingEmbedder",
    "IEmbedder",
    "SentenceTransformerEmbedder",
    "InMemoryMemoryStore",
    "LanceDbMemoryStore",
    "EmbeddingProvenanceTracker",
]
