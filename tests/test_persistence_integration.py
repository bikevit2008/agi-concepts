"""Integration tests: persistence wired into ConsciousnessLoop.

Verify that a tick:
- writes a `snapshot` event to the event store
- writes a `stimulus` event when a stimulus is processed
- saves a checkpoint at the configured frequency

Verify checkpoint/restore round-trip:
- save a snapshot, restart with empty state, restore from checkpoint,
  state matches the saved snapshot.
"""

import asyncio
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.config.flags import FeatureFlags
from src.config.settings import Settings
from src.contracts.governance import NullCircuitBreaker, NullGovernanceKernel
from src.contracts.persistence import NullCheckpoint, NullEventStore, Snapshot
from src.core.consciousness_loop import ConsciousnessLoop
from src.core.event_bus import EventBus
from src.core.runtime_state import RuntimeState
from src.engine.homeostatic_hysteresis import HomeostaticHysteresisEngine
from src.persistence.sqlite_checkpoint import SqliteCheckpoint
from src.persistence.sqlite_event_store import SqliteEventStore


def _make_loop(tmp_path: Path, **overrides) -> ConsciousnessLoop:
    settings = Settings()
    settings.persistence.event_store_path = str(tmp_path / "events.db")
    settings.persistence.checkpoint_path = str(tmp_path / "cp.db")
    settings.persistence.checkpoint_every_ticks = overrides.get("checkpoint_every_ticks", 2)
    settings.persistence.keep_last_n_snapshots = overrides.get("keep_last_n_snapshots", 20)
    flags = overrides.get("flags") or FeatureFlags()
    runtime_state = RuntimeState()
    hysteresis = HomeostaticHysteresisEngine.from_settings(settings.hysteresis)
    event_bus = EventBus()

    team = MagicMock()
    team.process_stimulus_sync.return_value = {"response": "ok"}
    team.reflect_sync.return_value = None
    team.spontaneous_thought_sync.return_value = None
    team.record_state_snapshot.return_value = None
    team.current_tick = 0
    team.memories = []
    team.emotion_history = []
    team.state_journal = []

    event_store = (
        SqliteEventStore(settings.persistence.event_store_path)
        if flags.persistence_enabled
        else NullEventStore()
    )
    checkpoint = (
        SqliteCheckpoint(settings.persistence.checkpoint_path)
        if flags.persistence_enabled
        else NullCheckpoint()
    )

    return ConsciousnessLoop(
        settings=settings,
        flags=flags,
        runtime_state=runtime_state,
        hysteresis=hysteresis,
        event_bus=event_bus,
        team=team,
        governance=NullGovernanceKernel(),
        circuit_breaker=NullCircuitBreaker(),
        event_store=event_store,
        checkpoint=checkpoint,
    )


def test_tick_writes_snapshot_event(tmp_path: Path):
    loop = _make_loop(tmp_path)
    asyncio.run(loop._tick())
    asyncio.run(loop._tick())

    events = list(loop.event_store.replay())
    snapshot_events = [e for e in events if e.event_type == "snapshot"]
    assert len(snapshot_events) >= 2
    assert snapshot_events[0].payload.get("tick") == 1
    loop.event_store.close()
    loop.checkpoint.close()


def test_tick_writes_stimulus_event_when_processed(tmp_path: Path):
    loop = _make_loop(tmp_path)
    asyncio.run(loop.submit_stimulus("Hello"))
    asyncio.run(loop._tick())

    events = list(loop.event_store.replay(event_type="stimulus"))
    assert len(events) == 1
    assert events[0].payload["stimulus"] == "Hello"
    loop.event_store.close()
    loop.checkpoint.close()


def test_event_store_close_truncates_wal(tmp_path: Path):
    db_path = tmp_path / "events.db"
    store = SqliteEventStore(str(db_path), wal_checkpoint_every_seconds=0.0)
    for i in range(10):
        store.append(i, "snapshot", {"tick": i})
    wal_path = tmp_path / "events.db-wal"
    store.close()
    assert not wal_path.exists() or wal_path.stat().st_size == 0


def test_periodic_checkpoint_saved(tmp_path: Path):
    loop = _make_loop(tmp_path, checkpoint_every_ticks=2)
    asyncio.run(loop._tick())
    # Tick 1: not a checkpoint tick
    assert loop.checkpoint.load_latest() is None
    asyncio.run(loop._tick())
    # Tick 2: checkpoint should be saved
    snap = loop.checkpoint.load_latest()
    assert snap is not None
    assert snap.tick == 2
    loop.event_store.close()
    loop.checkpoint.close()


def test_checkpoint_load_at_tick_and_prune(tmp_path: Path):
    cp = SqliteCheckpoint(str(tmp_path / "cp.db"))
    try:
        for tick in (2, 4, 6):
            cp.save(
                Snapshot(
                    tick=tick,
                    timestamp_ms=tick,
                    runtime_state={"temperature": tick},
                    hysteresis={},
                )
            )

        assert cp.load_at_tick(5).tick == 4
        assert cp.prune(before_tick=6) == 2
        assert cp.load_at_tick(5) is None
        assert cp.load_latest().tick == 6
    finally:
        cp.close()


def test_checkpoint_corrupt_payload_falls_back(tmp_path: Path):
    cp = SqliteCheckpoint(str(tmp_path / "cp.db"))
    try:
        conn = sqlite3.connect(str(tmp_path / "cp.db"))
        conn.execute(
            "INSERT INTO snapshots (tick, timestamp_ms, payload) VALUES (?, ?, ?)",
            (7, 123, "{not-json"),
        )
        conn.commit()
        conn.close()

        snap = cp.load_latest()
        assert snap.tick == 7
        assert snap.timestamp_ms == 123
        assert "_decode_error" in snap.extra
    finally:
        cp.close()


def test_periodic_checkpoint_prunes_to_keep_last_n(tmp_path: Path):
    loop = _make_loop(tmp_path, checkpoint_every_ticks=1, keep_last_n_snapshots=2)
    try:
        for _ in range(4):
            asyncio.run(loop._tick())

        latest = loop.checkpoint.load_latest()
        assert latest.tick == 4
        assert loop.checkpoint.load_at_tick(2) is None
        assert loop.checkpoint.load_at_tick(3).tick == 3
    finally:
        loop.event_store.close()
        loop.checkpoint.close()


def test_checkpoint_restore_round_trip(tmp_path: Path):
    """Save checkpoint, build a fresh loop, restore — state should match.

    We save the snapshot directly (bypassing _tick) so the saved values
    aren't perturbed by hysteresis dynamics — purpose here is to verify
    the persistence pipeline, not the loop math.
    """
    loop1 = _make_loop(tmp_path)
    loop1.runtime_state.temperature = 1.5
    loop1.runtime_state.energy_level = 0.4
    loop1.hysteresis.channels["stress"].value = 0.7
    loop1.team.memories = ["mem-A", "mem-B"]
    loop1.team.emotion_history = [{"primary_emotion": "joy"}]
    loop1._tick_count = 42

    snapshot = loop1._build_snapshot()
    loop1.checkpoint.save(snapshot)
    loop1.event_store.close()
    loop1.checkpoint.close()

    # Loop 2: fresh defaults; restore from disk
    loop2 = _make_loop(tmp_path)
    assert loop2.runtime_state.temperature == 0.7  # default before restore
    assert loop2.team.memories == []  # default

    restored = loop2.restore_from_checkpoint()
    assert restored is True
    assert abs(loop2.runtime_state.temperature - 1.5) < 1e-3
    assert abs(loop2.runtime_state.energy_level - 0.4) < 1e-3
    assert abs(loop2.hysteresis.channels["stress"].value - 0.7) < 1e-3
    assert loop2.team.memories == ["mem-A", "mem-B"]
    assert loop2.tick_count == 42
    loop2.event_store.close()
    loop2.checkpoint.close()


def test_persistence_disabled_no_writes(tmp_path: Path):
    flags = FeatureFlags()
    flags.persistence_enabled = False
    loop = _make_loop(tmp_path, flags=flags)
    asyncio.run(loop._tick())
    asyncio.run(loop._tick())
    asyncio.run(loop._tick())
    # NullEventStore returns empty replay
    assert list(loop.event_store.replay()) == []
    assert loop.checkpoint.load_latest() is None


def test_restore_from_empty_checkpoint_returns_false(tmp_path: Path):
    loop = _make_loop(tmp_path)
    assert loop.restore_from_checkpoint() is False
    loop.event_store.close()
    loop.checkpoint.close()


def test_restore_then_continue_keeps_event_sequence_monotonic(tmp_path: Path):
    loop1 = _make_loop(tmp_path, checkpoint_every_ticks=1)
    asyncio.run(loop1._tick())
    first_latest = loop1.event_store.latest_sequence()
    loop1.event_store.close()
    loop1.checkpoint.close()

    loop2 = _make_loop(tmp_path, checkpoint_every_ticks=1)
    try:
        assert loop2.restore_from_checkpoint() is True
        asyncio.run(loop2._tick())
        assert loop2.event_store.latest_sequence() > first_latest
    finally:
        loop2.event_store.close()
        loop2.checkpoint.close()
