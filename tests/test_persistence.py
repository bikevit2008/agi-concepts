"""Tests for SqliteEventStore and SqliteCheckpoint (Stage 4).

Cover:
- Append + replay round-trip preserves all fields.
- Filtering by event_type works.
- since_sequence / until_sequence / limit filters work.
- WAL pragmas are set on the connection.
- Checkpoint save/load round-trip preserves Snapshot.
- load_at_tick returns the latest snapshot at-or-before the requested tick.
- prune removes older snapshots.
- Both backends survive corrupted JSON in payload (graceful degrade).
- Null implementations conform to the contract and produce expected no-ops.
"""

import json
import sqlite3
from pathlib import Path


from src.contracts.persistence import (
    ICheckpoint,
    IEventStore,
    NullCheckpoint,
    NullEventStore,
    Snapshot,
)
from src.persistence.sqlite_checkpoint import SqliteCheckpoint
from src.persistence.sqlite_event_store import SqliteEventStore


# --- Event store -----------------------------------------------------------


def test_event_store_append_and_replay(tmp_path: Path):
    store = SqliteEventStore(str(tmp_path / "events.db"))
    seq1 = store.append(tick=1, event_type="stimulus", payload={"q": "hello"}, source="user")
    seq2 = store.append(tick=2, event_type="emotion", payload={"primary": "joy"})
    assert seq2 > seq1

    events = list(store.replay())
    assert len(events) == 2
    assert events[0].tick == 1
    assert events[0].event_type == "stimulus"
    assert events[0].payload == {"q": "hello"}
    assert events[0].source == "user"
    assert events[1].tick == 2
    assert events[1].event_type == "emotion"
    store.close()


def test_event_store_filter_by_type(tmp_path: Path):
    store = SqliteEventStore(str(tmp_path / "events.db"))
    store.append(1, "stimulus", {"q": "a"})
    store.append(1, "emotion", {"e": "joy"})
    store.append(2, "stimulus", {"q": "b"})

    stim = list(store.replay(event_type="stimulus"))
    assert len(stim) == 2
    assert all(e.event_type == "stimulus" for e in stim)
    store.close()


def test_event_store_filter_by_sequence_range(tmp_path: Path):
    store = SqliteEventStore(str(tmp_path / "events.db"))
    seqs = [store.append(i, "tick", {"i": i}) for i in range(10)]

    middle = list(store.replay(since_sequence=seqs[2], until_sequence=seqs[5]))
    assert [e.tick for e in middle] == [3, 4, 5]
    store.close()


def test_event_store_limit(tmp_path: Path):
    store = SqliteEventStore(str(tmp_path / "events.db"))
    for i in range(10):
        store.append(i, "tick", {"i": i})

    limited = list(store.replay(limit=3))
    assert len(limited) == 3
    store.close()


def test_event_store_latest_sequence(tmp_path: Path):
    store = SqliteEventStore(str(tmp_path / "events.db"))
    assert store.latest_sequence() == 0
    store.append(1, "x", {})
    store.append(2, "y", {})
    assert store.latest_sequence() == 2
    store.close()


def test_event_store_uses_wal_mode(tmp_path: Path):
    db_path = tmp_path / "events.db"
    store = SqliteEventStore(str(db_path))
    store.append(0, "init", {})
    store.close()

    # Verify WAL mode survives reconnect (it's persistent on the file)
    conn = sqlite3.connect(str(db_path))
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode.lower() == "wal"


def test_event_store_handles_unserializable_payload(tmp_path: Path):
    """Non-JSON-serialisable payload must NOT crash the store."""

    class Weird:
        pass

    store = SqliteEventStore(str(tmp_path / "events.db"))
    store.append(0, "weird", {"obj": Weird()})
    # default=str fallback should serialize as repr
    events = list(store.replay())
    assert len(events) == 1
    assert "obj" in events[0].payload
    store.close()


# --- Checkpoint ------------------------------------------------------------


def _make_snapshot(tick: int, **overrides) -> Snapshot:
    base = dict(
        tick=tick,
        timestamp_ms=1_000_000 + tick,
        runtime_state={"temperature": 0.7, "energy_level": 1.0},
        hysteresis={"channels": {"stress": {"value": 0.3}}},
        memories=["m1", "m2"],
        emotion_history=[{"primary_emotion": "joy"}],
        state_journal=[],
        extra={"foo": "bar"},
    )
    base.update(overrides)
    return Snapshot(**base)


def test_checkpoint_save_and_load_latest(tmp_path: Path):
    cp = SqliteCheckpoint(str(tmp_path / "cp.db"))
    cp.save(_make_snapshot(1))
    cp.save(_make_snapshot(2))

    loaded = cp.load_latest()
    assert loaded is not None
    assert loaded.tick == 2
    assert loaded.runtime_state["temperature"] == 0.7
    assert loaded.memories == ["m1", "m2"]
    cp.close()


def test_checkpoint_load_latest_empty(tmp_path: Path):
    cp = SqliteCheckpoint(str(tmp_path / "cp.db"))
    assert cp.load_latest() is None
    cp.close()


def test_checkpoint_load_at_tick_returns_at_or_before(tmp_path: Path):
    cp = SqliteCheckpoint(str(tmp_path / "cp.db"))
    cp.save(_make_snapshot(10))
    cp.save(_make_snapshot(20))
    cp.save(_make_snapshot(30))

    # Exact match
    assert cp.load_at_tick(20).tick == 20
    # In between → returns largest tick ≤ requested
    assert cp.load_at_tick(25).tick == 20
    # Before earliest → None
    assert cp.load_at_tick(5) is None
    cp.close()


def test_checkpoint_save_overrides_same_tick(tmp_path: Path):
    cp = SqliteCheckpoint(str(tmp_path / "cp.db"))
    cp.save(_make_snapshot(5, runtime_state={"temperature": 0.5}))
    cp.save(_make_snapshot(5, runtime_state={"temperature": 1.5}))
    loaded = cp.load_latest()
    assert loaded.runtime_state["temperature"] == 1.5
    cp.close()


def test_checkpoint_prune(tmp_path: Path):
    cp = SqliteCheckpoint(str(tmp_path / "cp.db"))
    for tick in [10, 20, 30, 40, 50]:
        cp.save(_make_snapshot(tick))

    pruned = cp.prune(before_tick=30)
    assert pruned == 2  # 10 and 20 removed

    # 30, 40, 50 remain
    remaining = []
    for tick in [10, 20, 30, 40, 50]:
        snap = cp.load_at_tick(tick)
        if snap and snap.tick == tick:
            remaining.append(tick)
    assert remaining == [30, 40, 50]
    cp.close()


def test_checkpoint_handles_corrupted_payload(tmp_path: Path):
    """Manually inject a corrupt row, ensure load doesn't crash."""
    cp = SqliteCheckpoint(str(tmp_path / "cp.db"))
    cp.save(_make_snapshot(1))
    # Manually corrupt the row
    with cp._lock:
        cp._conn.execute("UPDATE snapshots SET payload = '{not valid json' WHERE tick = 1")
    loaded = cp.load_latest()
    assert loaded is not None
    # Should have a sentinel error in extra
    assert "_decode_error" in loaded.extra
    cp.close()


def test_checkpoint_unknown_keys_go_to_extra(tmp_path: Path):
    """Forward-compat: unknown keys in payload → extra, not crash."""
    cp = SqliteCheckpoint(str(tmp_path / "cp.db"))
    snap = _make_snapshot(1)
    cp.save(snap)
    # Add a future field via direct UPDATE
    payload = json.dumps({**{
        "tick": 1,
        "timestamp_ms": 1_000_001,
        "runtime_state": {},
        "hysteresis": {},
    }, "future_field": "from_v4"})
    with cp._lock:
        cp._conn.execute("UPDATE snapshots SET payload = ? WHERE tick = 1", (payload,))
    loaded = cp.load_latest()
    assert loaded is not None
    assert loaded.extra.get("future_field") == "from_v4"
    cp.close()


# --- Null impls ------------------------------------------------------------


def test_null_event_store_returns_empty_replay():
    store = NullEventStore()
    s = store.append(1, "x", {})
    assert s > 0  # synthetic seq
    assert list(store.replay()) == []


def test_null_checkpoint_load_latest_is_none():
    cp = NullCheckpoint()
    cp.save(_make_snapshot(1))
    assert cp.load_latest() is None
    assert cp.prune(100) == 0


# --- Contract conformance --------------------------------------------------


def test_implementations_satisfy_contracts(tmp_path: Path):
    es: IEventStore = SqliteEventStore(str(tmp_path / "es.db"))
    cp: ICheckpoint = SqliteCheckpoint(str(tmp_path / "cp.db"))
    assert isinstance(es, IEventStore)
    assert isinstance(cp, ICheckpoint)
    es.close()
    cp.close()
