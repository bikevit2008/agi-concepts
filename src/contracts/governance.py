"""Governance contracts — rate limiting, circuit breakers, capability gating.

Two distinct responsibilities:
1. ICircuitBreaker — protects a single hysteresis channel from saturation lock.
   Tracks how long a channel has been pinned at its ceiling and trips when
   the saturation persists past a threshold (recoverable through reset).
2. IGovernanceKernel — deterministic policy enforcement on stimulation
   requests across the whole system: per-tick caps, per-agent caps,
   self-stimulation limits, capability checks.

Both are designed so the consciousness loop can call them in the hot path
without significant overhead (no LLM, no I/O).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Protocol, runtime_checkable


class GovernanceDecision(str, Enum):
    """Verdict from the governance kernel for a stimulation attempt."""

    ALLOW = "allow"
    DENY_PER_TICK_CAP = "deny_per_tick_cap"
    DENY_PER_AGENT_CAP = "deny_per_agent_cap"
    DENY_REFLECTION_CAP = "deny_reflection_cap"
    DENY_CIRCUIT_BREAKER = "deny_circuit_breaker"
    DENY_CAPABILITY = "deny_capability"
    DENY_BUDGET = "deny_budget"


@dataclass(frozen=True)
class StimulationRequest:
    """A request to stimulate a hysteresis channel.

    Carries enough context for the governance kernel to decide whether to
    allow, deny, or scale the intensity. Immutable so it can be safely
    passed around and logged.
    """

    agent: str  # source: "Emotion", "Reflection", "FeedbackLoop", etc.
    channel: str  # target: "stress", "fatigue", "euphoria", "pain"
    intensity: float  # signed: positive = harmful, negative = self-soothing
    tick: int  # tick number for tracing
    reason: Optional[str] = None  # human-readable rationale (optional)


@runtime_checkable
class ICircuitBreaker(Protocol):
    """Detects sustained channel saturation and signals an emergency.

    A channel is "saturated" when its value is pinned at or near 1.0
    (configurable). The circuit breaker counts consecutive ticks of
    saturation per channel and trips when the count exceeds a threshold,
    indicating that homeostatic mechanisms have failed and external
    intervention is needed.
    """

    def observe(self, channel: str, value: float, tick: int) -> bool:
        """Record current channel value. Returns True if circuit is tripped.

        Should be called every tick for every monitored channel.
        """
        ...

    def is_tripped(self, channel: Optional[str] = None) -> bool:
        """Check if any channel (or a specific one) is in tripped state."""
        ...

    def tripped_channels(self) -> List[str]:
        """Return list of currently-tripped channel names."""
        ...

    def reset(self, channel: Optional[str] = None) -> None:
        """Reset saturation counter. If channel is None, reset all channels."""
        ...

    def to_dict(self) -> Dict[str, object]:
        """Export state for snapshots / observability."""
        ...


@runtime_checkable
class IGovernanceKernel(Protocol):
    """Deterministic policy enforcement on stimulation requests.

    Stateful: tracks per-tick stimulation totals and resets each tick.
    Should be called from the consciousness loop's hot path, before any
    HysteresisEngine.stimulate() call.

    Pattern: stateful per-tick, FAIL-CLOSED on uncertainty.
    """

    def authorize(self, request: StimulationRequest) -> GovernanceDecision:
        """Check whether a stimulation request is allowed.

        Returns GovernanceDecision.ALLOW or a specific DENY_* reason.
        Does NOT mutate state — call record() after applying the stimulation.
        """
        ...

    def record(self, request: StimulationRequest) -> None:
        """Record an applied stimulation so subsequent authorize() calls
        see the cumulative impact within this tick."""
        ...

    def begin_tick(self, tick: int) -> None:
        """Reset per-tick counters. Should be called once per tick."""
        ...

    def end_tick(self, tick: int) -> Dict[str, object]:
        """Finalize the tick. Returns aggregated stats for observability."""
        ...

    def to_dict(self) -> Dict[str, object]:
        """Export config + current per-tick state."""
        ...


# ---------------------------------------------------------------------------
# Null implementations (Null Object Pattern)
# ---------------------------------------------------------------------------


class NullCircuitBreaker:
    """No-op circuit breaker: never trips, never blocks anything.

    Used when circuit breaker is disabled via feature flags.
    """

    def observe(self, channel: str, value: float, tick: int) -> bool:
        return False

    def is_tripped(self, channel: Optional[str] = None) -> bool:
        return False

    def tripped_channels(self) -> List[str]:
        return []

    def reset(self, channel: Optional[str] = None) -> None:
        return None

    def to_dict(self) -> Dict[str, object]:
        return {"type": "null"}


class NullGovernanceKernel:
    """No-op governance kernel: allows everything, records nothing.

    Used when governance is disabled via feature flags. Loop still has
    a stable interface to call.
    """

    def authorize(self, request: StimulationRequest) -> GovernanceDecision:
        return GovernanceDecision.ALLOW

    def record(self, request: StimulationRequest) -> None:
        return None

    def begin_tick(self, tick: int) -> None:
        return None

    def end_tick(self, tick: int) -> Dict[str, object]:
        return {}

    def to_dict(self) -> Dict[str, object]:
        return {"type": "null"}
