"""Persistence subsystem — event sourcing + checkpoint/restore.

Backed by SQLite in WAL mode for embedded, single-process deployments.
LanceDB (Stage 5) is used for vector memories specifically; the rest
of the system state lives in two SQLite WAL files (events.db,
checkpoints.db).
"""

from src.persistence.sqlite_checkpoint import SqliteCheckpoint
from src.persistence.sqlite_event_store import SqliteEventStore

__all__ = ["SqliteCheckpoint", "SqliteEventStore"]
