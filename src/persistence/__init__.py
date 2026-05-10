"""Persistence subsystem.

Stages covered:
- Stage 4: SQLite WAL event store + checkpoint
- Stage 5: LanceDB vector memory store + provenance
- Stage 6: Cost tracking (token + USD accounting)

Each subsystem has a Null fallback in src.contracts so the loop can
run with feature flags disabled.
"""

from src.persistence.cost_aware_agent import (
    AgnoModelInvoker,
    record_run_metrics,
)
from src.persistence.cost_tracker import (
    DEFAULT_MODEL_RATES,
    InMemoryCostTracker,
    ModelRate,
)
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
    # Stage 6
    "InMemoryCostTracker",
    "ModelRate",
    "DEFAULT_MODEL_RATES",
    "AgnoModelInvoker",
    "record_run_metrics",
]
