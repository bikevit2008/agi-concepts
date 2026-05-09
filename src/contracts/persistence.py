"""Persistence contracts — event sourcing & checkpoint/restore.

Two distinct responsibilities:
1. IEventStore — append-only event log (event sourcing pattern). Every
   significant change in the system gets logged with a sequence number,
   so the full trajectory can be replayed for debugging or reconstruction.
2. ICheckpoint — periodic snapshot of full system state (RuntimeState,
   hysteresis channels, memories, emotion history). Combined with the
   event log this gives us "snapshot + tail of events since snapshot"
   recovery, much faster than replaying from t=0.

Backend: SQLite WAL mode (PRAGMA journal_mode=WAL) for concurrency without
reader/writer blocking. Sequential writes ~3.6k/s, reads ~70k/s.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class EventRecord:
    """Single immutable record in the append-only event log.

    Fields:
        sequence: monotonically increasing global sequence number
        tick: consciousness loop tick (for correlation)
        event_type: short tag (e.g. "stimulus", "emotion", "snapshot")
        payload: arbitrary JSON-serialisable dict
        timestamp_ms: unix epoch millis
        source: subsystem that produced the event
    """

    sequence: int
    tick: int
    event_type: str
    payload: Dict[str, Any]
    timestamp_ms: int
    source: str = "system"


@dataclass
class Snapshot:
    """Full system state at a single tick. Restored on startup."""

    tick: int
    timestamp_ms: int
    runtime_state: Dict[str, Any]
    hysteresis: Dict[str, Any]
    memories: list = field(default_factory=list)
    emotion_history: list = field(default_factory=list)
    state_journal: list = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class IEventStore(Protocol):
    """Append-only event log with replay capability.

    Implementations should be safe to call from the loop's hot path.
    Failure to persist must NOT crash the loop — log and continue.
    """

    def append(
        self,
        tick: int,
        event_type: str,
        payload: Dict[str, Any],
        source: str = "system",
    ) -> int:
        """Append an event. Returns assigned sequence number."""
        ...

    def replay(
        self,
        since_sequence: int = 0,
        until_sequence: Optional[int] = None,
        event_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Iterable[EventRecord]:
        """Replay events in order. Generator-style for memory efficiency."""
        ...

    def latest_sequence(self) -> int:
        """Return the last assigned sequence number (0 if empty)."""
        ...

    def close(self) -> None:
        """Flush + close the underlying store."""
        ...


@runtime_checkable
class ICheckpoint(Protocol):
    """Full-state snapshots for fast restart.

    Strategy: append-only checkpoint table; restore loads the latest one.
    Older snapshots can be GC'd after their tick is no longer needed.
    """

    def save(self, snapshot: Snapshot) -> None:
        """Persist a snapshot. Implementations should be transactional."""
        ...

    def load_latest(self) -> Optional[Snapshot]:
        """Load the most recent snapshot, or None if no snapshots exist."""
        ...

    def load_at_tick(self, tick: int) -> Optional[Snapshot]:
        """Load the snapshot at exactly this tick, or the most recent
        snapshot at or before this tick."""
        ...

    def prune(self, before_tick: int) -> int:
        """Remove snapshots strictly before this tick. Returns count removed."""
        ...

    def close(self) -> None:
        """Flush + close the underlying store."""
        ...


# ---------------------------------------------------------------------------
# Null implementations (Null Object Pattern)
# ---------------------------------------------------------------------------


class NullEventStore:
    """No-op event store: discards everything, returns empty replay."""

    _seq: int = 0

    def append(
        self,
        tick: int,
        event_type: str,
        payload: Dict[str, Any],
        source: str = "system",
    ) -> int:
        self._seq += 1
        return self._seq

    def replay(
        self,
        since_sequence: int = 0,
        until_sequence: Optional[int] = None,
        event_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Iterable[EventRecord]:
        return iter([])

    def latest_sequence(self) -> int:
        return self._seq

    def close(self) -> None:
        return None


class NullCheckpoint:
    """No-op checkpoint: never saves, always loads None (no recovery)."""

    def save(self, snapshot: Snapshot) -> None:
        return None

    def load_latest(self) -> Optional[Snapshot]:
        return None

    def load_at_tick(self, tick: int) -> Optional[Snapshot]:
        return None

    def prune(self, before_tick: int) -> int:
        return 0

    def close(self) -> None:
        return None
