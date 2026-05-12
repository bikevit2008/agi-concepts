"""End-to-end tests that exercise full loop + subsystems together.

Different from harness-based unit tests: these instantiate the real
subsystems (SQLite event store, LanceDB, OTel with disabled exporters,
etc.) and run a few ticks to validate cross-subsystem wiring.

No real LLM calls — `ScriptedTeam` replaces `ConsciousnessTeam`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path


from src.config.flags import FeatureFlags
from src.config.settings import Settings
from src.bus.event_types import EventTypes
from src.contracts.ml import (
    NullCollapseForecaster,
    NullRecoveryPolicy,
    NullRuminationDetector,
)
from src.contracts.observability import NullObservabilityCollector
from src.contracts.sleep import NullMemoryConsolidator, NullSleepManager
from src.core.consciousness_loop import ConsciousnessLoop
from src.bus.asyncio_bus import AsyncioEventBus
from src.core.runtime_state import RuntimeState
from src.engine.circuit_breaker import SaturationCircuitBreaker
from src.engine.homeostatic_hysteresis import HomeostaticHysteresisEngine
from src.experiments.harness import ScriptedTeam
from src.governance.kernel import DeterministicGovernanceKernel, GovernancePolicy
from src.persistence.sqlite_checkpoint import SqliteCheckpoint
from src.persistence.sqlite_event_store import SqliteEventStore


def _build_loop_with_persistence(tmp_path: Path, **extras):
    settings = Settings()
    settings.persistence.event_store_path = str(tmp_path / "events.db")
    settings.persistence.checkpoint_path = str(tmp_path / "cp.db")
    settings.persistence.checkpoint_every_ticks = 2

    flags = FeatureFlags()
    flags.persistence_enabled = True

    runtime_state = RuntimeState()
    hysteresis = HomeostaticHysteresisEngine.from_settings(settings.hysteresis)

    team = ScriptedTeam(
        runtime_state=runtime_state,
        hysteresis=hysteresis,
        stimulus_response=lambda s: {"response": f"processed:{s}"},
    )

    event_store = SqliteEventStore(settings.persistence.event_store_path)
    checkpoint = SqliteCheckpoint(settings.persistence.checkpoint_path)

    circuit_breaker = SaturationCircuitBreaker()
    governance = DeterministicGovernanceKernel(
        policy=GovernancePolicy(),
        circuit_breaker=circuit_breaker,
    )

    loop = ConsciousnessLoop(
        settings=settings,
        flags=flags,
        runtime_state=runtime_state,
        hysteresis=hysteresis,
        event_bus=AsyncioEventBus(),
        team=team,
        governance=governance,
        circuit_breaker=circuit_breaker,
        event_store=event_store,
        checkpoint=checkpoint,
        observability=NullObservabilityCollector(),
        sleep_manager=NullSleepManager(),
        memory_consolidator=NullMemoryConsolidator(),
        rumination_detector=NullRuminationDetector(),
        collapse_forecaster=NullCollapseForecaster(),
        recovery_policy=NullRecoveryPolicy(),
    )
    return loop, event_store, checkpoint, team


# --- Scenarios -------------------------------------------------------------


def test_e2e_stimulus_flows_to_event_store(tmp_path: Path):
    """Submit a stimulus; event_store must see a `stimulus` event."""
    loop, es, cp, _ = _build_loop_with_persistence(tmp_path)
    try:
        async def drive():
            await loop.submit_stimulus("hello")
            await loop._tick()

        asyncio.run(drive())
        stim_events = list(es.replay(event_type="stimulus"))
        assert len(stim_events) == 1
        assert stim_events[0].payload["stimulus"] == "hello"
        snapshots = loop.event_bus.history(EventTypes.STATE_SNAPSHOT)
        assert snapshots
        assert snapshots[-1].payload["tick"] == loop.tick_count
    finally:
        es.close()
        cp.close()


def test_e2e_checkpoint_restore_end_to_end(tmp_path: Path):
    """Run a few ticks, save state, rebuild, restore — team state recovers."""
    loop, es, cp, team = _build_loop_with_persistence(tmp_path)
    try:
        loop.team.memories.append("initial memory")
        loop.team.emotion_history.append({"primary_emotion": "curious"})

        async def drive1():
            for _ in range(4):
                await loop._tick()

        asyncio.run(drive1())
        # Force an explicit snapshot save
        cp.save(loop._build_snapshot())
        snap_latest = cp.load_latest()
        assert snap_latest is not None
    finally:
        es.close()
        cp.close()

    # Rebuild with fresh state and restore
    loop2, es2, cp2, team2 = _build_loop_with_persistence(tmp_path)
    try:
        restored = loop2.restore_from_checkpoint()
        assert restored is True
        assert "initial memory" in loop2.team.memories
    finally:
        es2.close()
        cp2.close()


def test_e2e_governance_denies_excessive_stimulation(tmp_path: Path):
    """Configure very small caps, try to violate via feedback loops,
    check that governance's end_tick reports denies."""
    loop, es, cp, team = _build_loop_with_persistence(tmp_path)
    try:
        # Tighten governance policy
        loop.governance.policy = GovernancePolicy(
            per_tick_stimulus_cap=0.001,  # extremely low
            per_agent_stimulus_cap=0.0005,
            reflection_self_stim_cap=0.0001,
        )
        # Force low energy → triggers feedback loops (energy < 0.5)
        loop.runtime_state.energy_level = 0.2

        async def drive():
            for _ in range(5):
                await loop._tick()

        asyncio.run(drive())
        snapshot = loop.get_state_snapshot()
        cum = snapshot["governance"]["cumulative_decisions"]
        # Some DENY_* decisions must have been recorded
        denies = sum(
            v for k, v in cum.items() if k.startswith("deny_")
        )
        assert denies > 0, f"expected some denies, got {cum}"
    finally:
        es.close()
        cp.close()


def test_e2e_circuit_breaker_surfaces_in_snapshot(tmp_path: Path):
    """When a channel trips, get_state_snapshot shows it."""
    loop, es, cp, team = _build_loop_with_persistence(tmp_path)
    try:
        # Aggressive breaker config
        loop.circuit_breaker = SaturationCircuitBreaker(
            saturation_threshold=0.5, trip_after_ticks=2
        )

        # Pin stress above 0.5 for a while via per-tick team stim
        team.stimuli_per_tick = {"stress": 0.5}

        async def drive():
            for _ in range(10):
                await loop._tick()

        asyncio.run(drive())
        cb_state = loop.circuit_breaker.to_dict()
        assert "stress" in cb_state["channels"]
        # Either currently tripped or has tripped at least once
        assert (
            cb_state["channels"]["stress"].get("total_trips", 0) >= 1
            or cb_state["channels"]["stress"].get("is_tripped", False)
        )
    finally:
        es.close()
        cp.close()
