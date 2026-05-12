"""SQLite WAL append-only event store.

Schema (single events table with monotonic sequence):

    CREATE TABLE events (
        sequence    INTEGER PRIMARY KEY AUTOINCREMENT,
        tick        INTEGER NOT NULL,
        event_type  TEXT NOT NULL,
        payload     TEXT NOT NULL,        -- JSON
        timestamp_ms INTEGER NOT NULL,
        source      TEXT NOT NULL DEFAULT 'system'
    );
    CREATE INDEX idx_events_tick      ON events(tick);
    CREATE INDEX idx_events_type_tick ON events(event_type, tick);

Configuration (per dify-search SOTA reference, 2025):
- PRAGMA journal_mode=WAL  → reader/writer concurrency, sequential append
- PRAGMA synchronous=NORMAL → ~3.6k writes/s with safe ack semantics
- PRAGMA cache_size=-32000 (32 MB) → keeps hot pages in RAM
- PRAGMA busy_timeout=5000  → resilient to brief locks under load
- PRAGMA wal_autocheckpoint=0 → manual checkpoints scheduled by caller
                                (scheduler in `wal_checkpoint_every_seconds`)

The store is intentionally simple:
- One process, one file, one connection per `SqliteEventStore` instance.
- Threadsafe (`check_same_thread=False` + lock around writes).
- Failure to persist NEVER raises into the loop — errors are logged and
  the call returns a synthetic sequence number.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

import structlog

from src.contracts.persistence import EventRecord

logger = structlog.get_logger("consciousness.persistence.event_store")


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS events (
    sequence     INTEGER PRIMARY KEY AUTOINCREMENT,
    tick         INTEGER NOT NULL,
    event_type   TEXT NOT NULL,
    payload      TEXT NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    source       TEXT NOT NULL DEFAULT 'system'
);
CREATE INDEX IF NOT EXISTS idx_events_tick      ON events(tick);
CREATE INDEX IF NOT EXISTS idx_events_type_tick ON events(event_type, tick);
"""


def _open_connection(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(path),
        check_same_thread=False,
        isolation_level=None,  # autocommit
    )
    # WAL pragmas — see module docstring for rationale.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-32000")  # 32 MB
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA wal_autocheckpoint=0")
    conn.executescript(_SCHEMA_SQL)
    return conn


class SqliteEventStore:
    """`IEventStore` backed by a single SQLite WAL file."""

    def __init__(
        self,
        db_path: str,
        wal_checkpoint_every_seconds: float = 300.0,
    ) -> None:
        self.db_path = Path(db_path)
        self._conn = _open_connection(self.db_path)
        self._lock = threading.Lock()
        self._wal_checkpoint_interval = wal_checkpoint_every_seconds
        self._last_checkpoint_at = time.monotonic()

    def append(
        self,
        tick: int,
        event_type: str,
        payload: Dict[str, Any],
        source: str = "system",
    ) -> int:
        """Append an event. Returns assigned sequence number.

        Errors are caught + logged. We never want persistence problems
        to crash the consciousness loop.
        """
        try:
            payload_json = json.dumps(payload, default=str, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            logger.error("event_payload_json_error", error=str(e), event_type=event_type)
            payload_json = json.dumps({"_serialization_error": str(e)})

        timestamp_ms = int(time.time() * 1000)
        try:
            with self._lock:
                cursor = self._conn.execute(
                    "INSERT INTO events (tick, event_type, payload, timestamp_ms, source) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (tick, event_type, payload_json, timestamp_ms, source),
                )
                seq = int(cursor.lastrowid or 0)
            self._maybe_checkpoint()
            return seq
        except sqlite3.Error as e:
            logger.error(
                "event_store_append_failed",
                error=str(e),
                event_type=event_type,
                tick=tick,
            )
            return 0

    def replay(
        self,
        since_sequence: int = 0,
        until_sequence: Optional[int] = None,
        event_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Iterator[EventRecord]:
        """Generator-style replay for memory-efficient reads."""
        sql = "SELECT sequence, tick, event_type, payload, timestamp_ms, source FROM events WHERE sequence > ?"
        params: list[Any] = [since_sequence]
        if until_sequence is not None:
            sql += " AND sequence <= ?"
            params.append(until_sequence)
        if event_type is not None:
            sql += " AND event_type = ?"
            params.append(event_type)
        sql += " ORDER BY sequence ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        try:
            with self._lock:
                cursor = self._conn.execute(sql, params)
                rows = cursor.fetchall()
        except sqlite3.Error as e:
            logger.error("event_store_replay_failed", error=str(e))
            return

        for seq, tick, et, payload_json, ts, source in rows:
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                payload = {"_decode_error": payload_json[:200]}
            yield EventRecord(
                sequence=seq,
                tick=tick,
                event_type=et,
                payload=payload,
                timestamp_ms=ts,
                source=source,
            )

    def latest_sequence(self) -> int:
        try:
            with self._lock:
                row = self._conn.execute("SELECT MAX(sequence) FROM events").fetchone()
            return int(row[0] or 0)
        except sqlite3.Error as e:
            logger.error("event_store_latest_seq_failed", error=str(e))
            return 0

    def _maybe_checkpoint(self) -> None:
        """Periodically run `PRAGMA wal_checkpoint(RESTART)` to bound WAL growth."""
        now = time.monotonic()
        try:
            with self._lock:
                if now - self._last_checkpoint_at < self._wal_checkpoint_interval:
                    return
                self._conn.execute("PRAGMA wal_checkpoint(RESTART)")
                self._last_checkpoint_at = now
                logger.debug("wal_checkpoint_restart", path=str(self.db_path))
        except sqlite3.Error as e:
            logger.warning("wal_checkpoint_failed", error=str(e))

    def close(self) -> None:
        try:
            with self._lock:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self._conn.close()
        except sqlite3.Error as e:
            logger.warning("event_store_close_warning", error=str(e))


__all__ = ["SqliteEventStore"]
