"""Tests for the sleep subsystem (Stage 9)."""

import asyncio
from unittest.mock import MagicMock

import pytest

from src.contracts.memory import IMemoryStore, MemoryEntry
from src.contracts.sleep import (
    IMemoryConsolidator,
    ISleepManager,
    NullMemoryConsolidator,
    NullSleepManager,
    SleepDecision,
    SleepPhase,
    WakeState,
)
from src.engine.circadian import CircadianConfig, CircadianSleepManager
from src.engine.memory_consolidator import HebbianMemoryConsolidator
from src.persistence.embedder import HashingEmbedder
from src.persistence.memory_store import InMemoryMemoryStore


# --- CircadianSleepManager -------------------------------------------------


def test_starts_awake():
    sm = CircadianSleepManager()
    decision = sm.update(0, dt_seconds=0.0, runtime_state={}, hysteresis_state={})
    assert decision.wake_state == WakeState.AWAKE
    assert decision.phase == SleepPhase.NONE


def test_pressure_builds_when_awake():
    sm = CircadianSleepManager(config=CircadianConfig(awake_seconds=10.0, sleep_seconds=10.0))
    sm.update(0, 5.0, {}, {})
    sm.update(1, 5.0, {}, {})
    decision = sm.update(2, 1.0, {}, {})
    # After ~11s of awake time at awake_seconds=10 → pressure climbed to ≥ 1.0
    assert decision.sleep_pressure > 0.5


def test_transitions_to_sleep_under_pressure():
    sm = CircadianSleepManager(
        config=CircadianConfig(
            awake_seconds=1.0,  # rapid pressure build
            sleep_seconds=10.0,
            pressure_to_sleep_threshold=0.3,
        )
    )
    decisions = []
    for tick in range(10):
        decisions.append(sm.update(tick, 1.0, {}, {}))
    states = [d.wake_state for d in decisions]
    # Eventually transitions out of AWAKE
    assert any(s in (WakeState.DROWSY, WakeState.SLEEPING) for s in states)


def test_force_sleep_then_force_wake():
    sm = CircadianSleepManager()
    sm.force_sleep()
    sm.update(0, 0.5, {}, {})
    sm.update(1, 6.0, {}, {})  # past the 5s drowsy threshold
    state_after_force_sleep = sm._wake_state
    assert state_after_force_sleep == WakeState.SLEEPING

    sm.force_wake()
    sm.update(2, 0.5, {}, {})
    sm.update(3, 6.0, {}, {})
    assert sm._wake_state == WakeState.AWAKE


def test_suppress_llm_during_sleep_when_configured():
    sm = CircadianSleepManager(
        config=CircadianConfig(suppress_llm_during_sleep=True),
    )
    sm.force_sleep()
    sm.update(0, 0.5, {}, {})
    sm.update(1, 6.0, {}, {})  # SLEEPING
    decision = sm.update(2, 0.5, {}, {})
    assert decision.suppress_llm_calls is True


def test_to_dict_exposes_state():
    sm = CircadianSleepManager()
    sm.update(0, 1.0, {}, {})
    d = sm.to_dict()
    assert d["type"] == "circadian_two_process"
    assert "process_s" in d
    assert d["wake_state"] in (WakeState.AWAKE.value, WakeState.DROWSY.value)


def test_satisfies_contract():
    sm: ISleepManager = CircadianSleepManager()
    assert isinstance(sm, ISleepManager)


def test_null_sleep_manager_always_awake():
    sm: ISleepManager = NullSleepManager()
    decision = sm.update(0, 1000.0, {}, {})
    assert decision.wake_state == WakeState.AWAKE
    assert decision.suppress_llm_calls is False


# --- HebbianMemoryConsolidator --------------------------------------------


def _store_with(entries: list[MemoryEntry]) -> InMemoryMemoryStore:
    s = InMemoryMemoryStore(embedder=HashingEmbedder())
    for e in entries:
        s.store(e)
    return s


def test_consolidate_nrem_strengthens_paired_memories():
    store = _store_with(
        [
            MemoryEntry(id="", content="A", source="s",
                        emotion_associations={"joy": 0.5}, confidence=0.5),
            MemoryEntry(id="", content="B", source="s",
                        emotion_associations={"joy": 0.4}, confidence=0.5),
        ]
    )
    c = HebbianMemoryConsolidator(memory_store=store, nrem_strengthen_factor=2.0)
    pre = [e.confidence for e in store.all_entries()]
    stats = c.consolidate_nrem(memory_ids=[])
    assert stats["consolidated"] == 1  # one pair strengthened
    post = [e.confidence for e in store.all_entries()]
    # Both should be capped at 1.0 after multiplying by 2.0
    assert all(p > 0.5 for p in post)
    assert max(post) == 1.0


def test_consolidate_nrem_no_pairs_no_change():
    store = _store_with(
        [
            MemoryEntry(id="", content="A", source="s",
                        emotion_associations={"joy": 0.5}, confidence=0.5),
            MemoryEntry(id="", content="B", source="s",
                        emotion_associations={"sadness": 0.5}, confidence=0.5),
        ]
    )
    c = HebbianMemoryConsolidator(memory_store=store)
    stats = c.consolidate_nrem(memory_ids=[])
    # No shared emotions — no strengthening
    assert stats["consolidated"] == 0


def test_consolidate_rem_creates_abstraction_for_clusters():
    store = _store_with(
        [
            MemoryEntry(id="", content="A1", source="s",
                        emotion_associations={"joy": 0.9}, confidence=0.5),
            MemoryEntry(id="", content="A2", source="s",
                        emotion_associations={"joy": 0.8}, confidence=0.5),
            MemoryEntry(id="", content="A3", source="s",
                        emotion_associations={"joy": 0.7}, confidence=0.5),
            MemoryEntry(id="", content="B1", source="s",
                        emotion_associations={"sadness": 0.6}, confidence=0.5),
        ]
    )
    pre_count = store.count()
    c = HebbianMemoryConsolidator(memory_store=store, rem_min_cluster_size=3)
    stats = c.consolidate_rem(memory_ids=[])
    # Exactly one cluster with ≥3 members → one abstraction stored
    assert stats["consolidated"] == 1
    assert store.count() == pre_count + 1
    # The new memory should be tagged as an abstraction
    new = next(e for e in store.all_entries() if e.source == "rem_consolidation")
    assert "[abstraction:joy]" in new.content


def test_consolidate_rem_skips_below_threshold_cluster():
    store = _store_with(
        [
            MemoryEntry(id="", content="A1", source="s",
                        emotion_associations={"joy": 0.9}, confidence=0.5),
            MemoryEntry(id="", content="A2", source="s",
                        emotion_associations={"joy": 0.8}, confidence=0.5),
        ]
    )
    c = HebbianMemoryConsolidator(memory_store=store, rem_min_cluster_size=3)
    stats = c.consolidate_rem(memory_ids=[])
    # 2 < 3 → no abstraction
    assert stats["consolidated"] == 0


def test_null_consolidator_no_op():
    c: IMemoryConsolidator = NullMemoryConsolidator()
    assert c.consolidate_nrem(["a"]) == {"phase": "nrem", "consolidated": 0}
    assert c.consolidate_rem(["b"]) == {"phase": "rem", "consolidated": 0}


def test_consolidator_satisfies_contract():
    store = InMemoryMemoryStore(embedder=HashingEmbedder())
    c: IMemoryConsolidator = HebbianMemoryConsolidator(memory_store=store)
    assert isinstance(c, IMemoryConsolidator)


# --- Loop integration ------------------------------------------------------


def test_loop_suppresses_llm_during_sleep():
    """When sleep_manager says suppress, team.process_stimulus_sync is NOT called."""
    from src.config.flags import FeatureFlags
    from src.config.settings import Settings
    from src.contracts.governance import NullCircuitBreaker, NullGovernanceKernel
    from src.contracts.observability import NullObservabilityCollector
    from src.contracts.persistence import NullCheckpoint, NullEventStore
    from src.core.consciousness_loop import ConsciousnessLoop
    from src.bus.asyncio_bus import AsyncioEventBus
    from src.core.runtime_state import RuntimeState
    from src.engine.homeostatic_hysteresis import HomeostaticHysteresisEngine

    settings = Settings()
    flags = FeatureFlags()
    flags.sleep_mode_enabled = True

    sleep_manager = MagicMock()
    sleep_manager.update.return_value = SleepDecision(
        wake_state=WakeState.SLEEPING,
        phase=SleepPhase.NREM,
        sleep_pressure=0.9,
        circadian_phase=0.5,
        suppress_llm_calls=True,
    )

    team = MagicMock()
    team.process_stimulus_sync.return_value = {"response": "should not be called"}
    team.reflect_sync.return_value = None
    team.spontaneous_thought_sync.return_value = None
    team.record_state_snapshot.return_value = None
    team.current_tick = 0
    team.memories = []
    team.emotion_history = []
    team.state_journal = []

    loop = ConsciousnessLoop(
        settings=settings,
        flags=flags,
        runtime_state=RuntimeState(),
        hysteresis=HomeostaticHysteresisEngine.from_settings(settings.hysteresis),
        event_bus=AsyncioEventBus(),
        team=team,
        governance=NullGovernanceKernel(),
        circuit_breaker=NullCircuitBreaker(),
        event_store=NullEventStore(),
        checkpoint=NullCheckpoint(),
        observability=NullObservabilityCollector(),
        sleep_manager=sleep_manager,
    )

    class CountingQueue(asyncio.Queue[str]):
        def __init__(self) -> None:
            super().__init__()
            self.get_nowait_calls = 0
            self.put_calls = 0

        def get_nowait(self) -> str:
            self.get_nowait_calls += 1
            return super().get_nowait()

        async def put(self, item: str) -> None:
            self.put_calls += 1
            await super().put(item)

    queue = CountingQueue()
    loop._stimulus_queue = queue

    asyncio.run(loop.submit_stimulus("hello"))
    asyncio.run(loop._tick())
    asyncio.run(loop._tick())

    # team.process_stimulus_sync must not have been called
    team.process_stimulus_sync.assert_not_called()
    # Stimulus should stay queued for wake without dequeue/requeue churn
    assert loop._stimulus_queue.qsize() == 1
    assert queue.get_nowait_calls == 0
    assert queue.put_calls == 1
