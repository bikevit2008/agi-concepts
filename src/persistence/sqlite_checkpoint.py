"""SQLite-backed snapshot store (`ICheckpoint`).

A snapshot is the FULL state required to resurrect the consciousness
loop from a crash:
- runtime_state (dict of float fields)
- hysteresis (channel values + hidden state)
- memories (list of strings)
- emotion_history (recent emotions)
- state_journal (recent snapshots)
- extra (arbitrary forward-compat metadata)

Schema:

    CREATE TABLE snapshots (
        tick         INTEGER PRIMARY KEY,
        timestamp_ms INTEGER NOT NULL,
        payload      TEXT NOT NULL  -- JSON of full Snapshot
    );

Each snapshot is a single row. `load_latest()` is `SELECT * ORDER BY tick
DESC LIMIT 1`. `prune(before_tick)` removes everything older than
`before_tick` so the snapshot store doesn't grow unbounded.

Same WAL pragmas as the event store; same fail-soft behavior.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import structlog

from src.contracts.persistence import Snapshot

logger = structlog.get_logger("consciousness.persistence.checkpoint")


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS snapshots (
    tick         INTEGER PRIMARY KEY,
    timestamp_ms INTEGER NOT NULL,
    payload      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(timestamp_ms);
"""


def _open_connection(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(path),
        check_same_thread=False,
        isolation_level=None,
    )
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-32000")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(_SCHEMA_SQL)
    return conn


def _snapshot_to_payload(snapshot: Snapshot) -> str:
    return json.dumps(asdict(snapshot), default=str, ensure_ascii=False)


def _snapshot_from_payload(payload: str, fallback_tick: int, fallback_ts: int) -> Snapshot:
    """Decode a stored payload into a Snapshot dataclass.

    Resilient to schema drift: unknown keys go into `extra`, missing
    keys default sensibly.
    """
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return Snapshot(
            tick=fallback_tick,
            timestamp_ms=fallback_ts,
            runtime_state={},
            hysteresis={},
            extra={"_decode_error": payload[:200]},
        )

    runtime_state = data.get("runtime_state") or {}
    hysteresis = data.get("hysteresis") or {}
    memories = data.get("memories") or []
    emotion_history = data.get("emotion_history") or []
    state_journal = data.get("state_journal") or []

    known = {
        "tick",
        "timestamp_ms",
        "runtime_state",
        "hysteresis",
        "memories",
        "emotion_history",
        "state_journal",
        "extra",
    }
    extra = data.get("extra") or {}
    for k, v in data.items():
        if k not in known:
            extra[k] = v

    return Snapshot(
        tick=int(data.get("tick", fallback_tick)),
        timestamp_ms=int(data.get("timestamp_ms", fallback_ts)),
        runtime_state=runtime_state,
        hysteresis=hysteresis,
        memories=memories,
        emotion_history=emotion_history,
        state_journal=state_journal,
        extra=extra,
    )


class SqliteCheckpoint:
    """`ICheckpoint` backed by a single SQLite WAL file."""

    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self._conn = _open_connection(self.db_path)
        self._lock = threading.Lock()

    def save(self, snapshot: Snapshot) -> None:
        """Persist a snapshot. INSERT OR REPLACE — same tick overrides."""
        if snapshot.timestamp_ms <= 0:
            snapshot.timestamp_ms = int(time.time() * 1000)
        payload = _snapshot_to_payload(snapshot)
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT OR REPLACE INTO snapshots (tick, timestamp_ms, payload) VALUES (?, ?, ?)",
                    (snapshot.tick, snapshot.timestamp_ms, payload),
                )
        except sqlite3.Error as e:
            logger.error("checkpoint_save_failed", error=str(e), tick=snapshot.tick)

    def load_latest(self) -> Optional[Snapshot]:
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT tick, timestamp_ms, payload FROM snapshots ORDER BY tick DESC LIMIT 1"
                ).fetchone()
        except sqlite3.Error as e:
            logger.error("checkpoint_load_latest_failed", error=str(e))
            return None
        if not row:
            return None
        tick, ts, payload = row
        return _snapshot_from_payload(payload, fallback_tick=tick, fallback_ts=ts)

    def load_at_tick(self, tick: int) -> Optional[Snapshot]:
        """Load the snapshot at exactly `tick`, or the latest snapshot at
        or before `tick` if no exact match exists."""
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT tick, timestamp_ms, payload FROM snapshots "
                    "WHERE tick <= ? ORDER BY tick DESC LIMIT 1",
                    (tick,),
                ).fetchone()
        except sqlite3.Error as e:
            logger.error("checkpoint_load_at_tick_failed", error=str(e), tick=tick)
            return None
        if not row:
            return None
        loaded_tick, ts, payload = row
        return _snapshot_from_payload(payload, fallback_tick=loaded_tick, fallback_ts=ts)

    def prune(self, before_tick: int) -> int:
        try:
            with self._lock:
                cursor = self._conn.execute(
                    "DELETE FROM snapshots WHERE tick < ?", (before_tick,)
                )
                count = cursor.rowcount or 0
        except sqlite3.Error as e:
            logger.error("checkpoint_prune_failed", error=str(e), before_tick=before_tick)
            return 0
        if count > 0:
            logger.info("checkpoint_pruned", count=count, before_tick=before_tick)
        return count

    def close(self) -> None:
        try:
            with self._lock:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self._conn.close()
        except sqlite3.Error as e:
            logger.warning("checkpoint_close_warning", error=str(e))


__all__ = ["SqliteCheckpoint"]
