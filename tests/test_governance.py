"""Tests for DeterministicGovernanceKernel (Stage 3).

Cover:
- Negative intensity always allowed (self-soothing).
- Positive intensity respects per_tick / per_agent / reflection caps.
- Circuit breaker integration: tripped channel rejects positive stim.
- begin_tick / end_tick reset per-tick counters and report decisions.
- Null kernel (Null Object) allows everything and records nothing.
- Static contract conformance.
"""

import pytest

from src.contracts.governance import (
    GovernanceDecision,
    NullCircuitBreaker,
    NullGovernanceKernel,
    StimulationRequest,
)
from src.engine.circuit_breaker import SaturationCircuitBreaker
from src.governance.kernel import DeterministicGovernanceKernel, GovernancePolicy


def _req(agent: str, channel: str, intensity: float, tick: int = 0) -> StimulationRequest:
    return StimulationRequest(agent=agent, channel=channel, intensity=intensity, tick=tick)


def test_negative_intensity_always_allowed():
    k = DeterministicGovernanceKernel()
    k.begin_tick(0)
    # Far exceeds any cap, but negative — must allow
    assert k.authorize(_req("Reflection", "stress", -10.0)) == GovernanceDecision.ALLOW
    assert k.authorize(_req("Emotion", "fatigue", -1.0)) == GovernanceDecision.ALLOW


def test_per_tick_cap_enforced():
    k = DeterministicGovernanceKernel(
        policy=GovernancePolicy(per_tick_stimulus_cap=0.3, per_agent_stimulus_cap=10.0)
    )
    k.begin_tick(0)
    # Three at 0.1 each — total 0.3 — last one boundary-allowed
    for _ in range(3):
        d = k.authorize(_req("Emotion", "stress", 0.1))
        k.record(_req("Emotion", "stress", 0.1)) if d == GovernanceDecision.ALLOW else None
        assert d == GovernanceDecision.ALLOW
    # Next 0.05 must be denied — would push total over 0.3
    assert k.authorize(_req("Emotion", "stress", 0.05)) == GovernanceDecision.DENY_PER_TICK_CAP


def test_per_agent_cap_enforced():
    k = DeterministicGovernanceKernel(
        policy=GovernancePolicy(per_tick_stimulus_cap=10.0, per_agent_stimulus_cap=0.2)
    )
    k.begin_tick(0)
    # 0.15 from agent A — allowed
    d1 = k.authorize(_req("AgentA", "stress", 0.15))
    assert d1 == GovernanceDecision.ALLOW
    k.record(_req("AgentA", "stress", 0.15))
    # Another 0.1 from same agent — would push over 0.2
    d2 = k.authorize(_req("AgentA", "fatigue", 0.1))
    assert d2 == GovernanceDecision.DENY_PER_AGENT_CAP
    # Different agent — allowed (under per_tick cap)
    d3 = k.authorize(_req("AgentB", "stress", 0.1))
    assert d3 == GovernanceDecision.ALLOW


def test_reflection_cap_stricter_than_per_agent():
    k = DeterministicGovernanceKernel(
        policy=GovernancePolicy(
            per_tick_stimulus_cap=10.0,
            per_agent_stimulus_cap=0.5,
            reflection_self_stim_cap=0.1,
        )
    )
    k.begin_tick(0)
    # Reflection cap is 0.1
    d = k.authorize(_req("Reflection", "stress", 0.05))
    assert d == GovernanceDecision.ALLOW
    k.record(_req("Reflection", "stress", 0.05))
    # Another 0.1 from Reflection — would total 0.15 > 0.1 reflection cap
    d2 = k.authorize(_req("Reflection", "fatigue", 0.1))
    assert d2 == GovernanceDecision.DENY_REFLECTION_CAP
    # Same intensity from non-reflection agent — allowed
    d3 = k.authorize(_req("Emotion", "fatigue", 0.1))
    assert d3 == GovernanceDecision.ALLOW


def test_circuit_breaker_blocks_positive_stim_on_tripped_channel():
    cb = SaturationCircuitBreaker(saturation_threshold=0.9, trip_after_ticks=2)
    # Trip the breaker on "stress"
    cb.observe("stress", 0.99, 0)
    cb.observe("stress", 0.99, 1)
    assert cb.is_tripped("stress")

    k = DeterministicGovernanceKernel(circuit_breaker=cb)
    k.begin_tick(2)
    # Positive stim on tripped channel — denied
    assert k.authorize(_req("Emotion", "stress", 0.05)) == GovernanceDecision.DENY_CIRCUIT_BREAKER
    # Positive stim on different (untripped) channel — allowed
    assert k.authorize(_req("Emotion", "fatigue", 0.05)) == GovernanceDecision.ALLOW
    # Negative stim on tripped channel — allowed (self-soothing during recovery)
    assert k.authorize(_req("Reflection", "stress", -0.05)) == GovernanceDecision.ALLOW


def test_begin_tick_resets_counters():
    k = DeterministicGovernanceKernel(
        policy=GovernancePolicy(per_tick_stimulus_cap=0.2)
    )
    k.begin_tick(0)
    # Saturate this tick's budget
    for _ in range(2):
        k.record(_req("A", "stress", 0.1))
    # Tick over — counters should reset
    stats = k.end_tick(0)
    assert stats["total_positive"] == pytest.approx(0.2, rel=1e-6)
    k.begin_tick(1)
    # Same load on a fresh tick should work again
    assert k.authorize(_req("A", "stress", 0.15)) == GovernanceDecision.ALLOW


def test_end_tick_reports_decisions():
    k = DeterministicGovernanceKernel(
        policy=GovernancePolicy(per_tick_stimulus_cap=0.1)
    )
    k.begin_tick(0)
    # 1 ALLOW, 1 DENY_PER_TICK_CAP
    assert k.authorize(_req("A", "stress", 0.1)) == GovernanceDecision.ALLOW
    k.record(_req("A", "stress", 0.1))
    assert k.authorize(_req("A", "fatigue", 0.05)) == GovernanceDecision.DENY_PER_TICK_CAP
    stats = k.end_tick(0)
    assert stats["decisions"][GovernanceDecision.ALLOW.value] == 1
    assert stats["decisions"][GovernanceDecision.DENY_PER_TICK_CAP.value] == 1


def test_null_kernel_always_allows():
    k = NullGovernanceKernel()
    k.begin_tick(0)
    assert k.authorize(_req("Whoever", "anything", 999.0)) == GovernanceDecision.ALLOW
    k.record(_req("Whoever", "anything", 999.0))
    stats = k.end_tick(0)
    assert stats == {}  # no aggregations


def test_null_circuit_breaker_never_trips():
    cb = NullCircuitBreaker()
    for tick in range(1000):
        assert cb.observe("stress", 1.0, tick) is False
    assert not cb.is_tripped()
    assert cb.tripped_channels() == []


def test_satisfies_contract():
    from src.contracts.governance import IGovernanceKernel
    k: IGovernanceKernel = DeterministicGovernanceKernel()
    assert isinstance(k, IGovernanceKernel)
