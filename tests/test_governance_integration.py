"""Integration tests: governance kernel wired into ConsciousnessLoop.

These tests do NOT spin up real LLM agents — they verify the governance
gate sits between the loop and the hysteresis engine, and that the
circuit breaker observes channel state every tick.
"""

import asyncio
from unittest.mock import MagicMock


from src.config.flags import FeatureFlags
from src.config.settings import Settings
from src.contracts.governance import GovernanceDecision, NullGovernanceKernel
from src.core.consciousness_loop import ConsciousnessLoop, gated_stimulate
from src.bus.asyncio_bus import AsyncioEventBus
from src.core.runtime_state import RuntimeState
from src.engine.circuit_breaker import SaturationCircuitBreaker
from src.engine.homeostatic_hysteresis import HomeostaticHysteresisEngine
from src.governance.kernel import DeterministicGovernanceKernel, GovernancePolicy


def _make_loop(governance, circuit_breaker, flags=None) -> ConsciousnessLoop:
    """Construct a loop with stub team & event bus for testing."""
    settings = Settings()
    flags = flags or FeatureFlags()
    runtime_state = RuntimeState()
    hysteresis = HomeostaticHysteresisEngine.from_settings(settings.hysteresis)
    event_bus = AsyncioEventBus()

    # Stub the team to skip LLM agents
    team = MagicMock()
    team.process_stimulus_sync.return_value = {"response": "ok"}
    team.reflect_sync.return_value = None
    team.spontaneous_thought_sync.return_value = None
    team.record_state_snapshot.return_value = None
    team.current_tick = 0

    return ConsciousnessLoop(
        settings=settings,
        flags=flags,
        runtime_state=runtime_state,
        hysteresis=hysteresis,
        event_bus=event_bus,
        team=team,
        governance=governance,
        circuit_breaker=circuit_breaker,
    )


def test_gated_stimulate_allows_within_cap():
    settings = Settings()
    hysteresis = HomeostaticHysteresisEngine.from_settings(settings.hysteresis)
    governance = DeterministicGovernanceKernel(
        policy=GovernancePolicy(per_tick_stimulus_cap=0.5, per_agent_stimulus_cap=0.5)
    )
    governance.begin_tick(0)

    pre = hysteresis.channels["stress"].value
    decision = gated_stimulate(
        hysteresis,
        governance,
        agent="Test",
        channel="stress",
        intensity=0.1,
        tick=0,
    )
    assert decision == GovernanceDecision.ALLOW
    # Hysteresis state should have been bumped (pending_stimulus)
    assert hysteresis.channels["stress"]._pending_stimulus > pre


def test_gated_stimulate_denies_over_cap():
    """Over-cap stimulation must be denied AND must not mutate hysteresis."""
    settings = Settings()
    hysteresis = HomeostaticHysteresisEngine.from_settings(settings.hysteresis)
    # per_tick is the wide cap; per_agent narrower — narrower deny will fire first
    governance = DeterministicGovernanceKernel(
        policy=GovernancePolicy(per_tick_stimulus_cap=10.0, per_agent_stimulus_cap=0.05)
    )
    governance.begin_tick(0)

    pre_pending = hysteresis.channels["stress"]._pending_stimulus
    decision = gated_stimulate(
        hysteresis,
        governance,
        agent="Test",
        channel="stress",
        intensity=0.1,  # exceeds per_agent cap of 0.05
        tick=0,
    )
    assert decision == GovernanceDecision.DENY_PER_AGENT_CAP
    # Hysteresis state must NOT have changed
    assert hysteresis.channels["stress"]._pending_stimulus == pre_pending


def test_loop_calls_begin_and_end_tick():
    governance = DeterministicGovernanceKernel()
    cb = SaturationCircuitBreaker()
    loop = _make_loop(governance, cb)

    # Spy on begin_tick / end_tick
    begin_calls = []
    end_calls = []
    orig_begin = governance.begin_tick
    orig_end = governance.end_tick

    def begin_spy(tick: int):
        begin_calls.append(tick)
        orig_begin(tick)

    def end_spy(tick: int):
        end_calls.append(tick)
        return orig_end(tick)

    governance.begin_tick = begin_spy  # type: ignore[method-assign]
    governance.end_tick = end_spy  # type: ignore[method-assign]

    asyncio.run(loop._tick())

    # _tick() increments _tick_count to 1 before calling _tick_inner
    assert begin_calls == [1]
    assert end_calls == [1]


def test_loop_propagates_tick_to_team():
    governance = NullGovernanceKernel()
    cb = SaturationCircuitBreaker()
    loop = _make_loop(governance, cb)

    asyncio.run(loop._tick())
    asyncio.run(loop._tick())

    # Team's current_tick should have been bumped
    assert loop.team.current_tick == 2


def test_loop_observes_circuit_breaker():
    """Loop should call circuit_breaker.observe() each tick.

    Verify by observing the per-channel `total_trips` counter increase.
    Note: hysteresis.tick() decays the value before observation, so we
    have to re-pin it each iteration to keep it at saturation.
    """
    governance = NullGovernanceKernel()
    cb = SaturationCircuitBreaker(
        saturation_threshold=0.9, trip_after_ticks=2, reset_below=0.1
    )
    loop = _make_loop(governance, cb)

    # Pin stress at saturation, ride out a few ticks
    for _ in range(4):
        loop.hysteresis.channels["stress"].value = 0.99
        asyncio.run(loop._tick())

    # Some snapshot of breaker state must show the trip happened
    snapshot = cb.to_dict()
    stress_state = snapshot["channels"].get("stress", {})
    assert stress_state.get("total_trips", 0) >= 1


def test_circuit_breaker_disabled_observes_nothing():
    governance = NullGovernanceKernel()
    cb = SaturationCircuitBreaker(saturation_threshold=0.0001, trip_after_ticks=1)
    flags = FeatureFlags()
    flags.circuit_breaker_enabled = False
    loop = _make_loop(governance, cb, flags=flags)

    loop.hysteresis.channels["stress"].value = 1.0
    asyncio.run(loop._tick())
    asyncio.run(loop._tick())
    asyncio.run(loop._tick())

    # Even with channel pinned at 1.0, breaker was never observed
    assert not cb.is_tripped()


def test_governance_disabled_skips_begin_tick():
    governance = MagicMock(spec=DeterministicGovernanceKernel)
    cb = SaturationCircuitBreaker()
    flags = FeatureFlags()
    flags.governance_enabled = False
    loop = _make_loop(governance, cb, flags=flags)

    asyncio.run(loop._tick())

    governance.begin_tick.assert_not_called()
    governance.end_tick.assert_not_called()


def test_loop_snapshot_includes_governance_state():
    governance = DeterministicGovernanceKernel()
    cb = SaturationCircuitBreaker()
    loop = _make_loop(governance, cb)

    snap = loop.get_state_snapshot()
    assert "governance" in snap
    assert snap["governance"]["type"] == "deterministic"
    assert "circuit_breaker" in snap
    assert snap["circuit_breaker"]["type"] == "saturation"
