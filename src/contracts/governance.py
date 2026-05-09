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

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


class GovernanceDecision(str, Enum):
    """Verdict from the governance kernel for a stimulation attempt."""

    ALLOW = "allow"
    DENY_PER_TICK_CAP = "deny_per_tick_cap"
    DENY_PER_AGENT_CAP = "deny_per_agent_cap"
    DENY_REFLECTION_CAP = "deny_reflection_cap"
    DENY_CIRCUIT_BREAKER = "deny_circuit_breaker"
    DENY_CAPABILITY = "deny_capability"
    DENY_BUDGET = "deny_budget"
    DENY_CONSTITUTION = "deny_constitution"
    WARN_CONSTITUTION = "warn_constitution"


class PolicySeverity(str, Enum):
    """Severity tier of a constitutional policy.

    Mapping to graduated responses:
        CRITICAL → DENY  (block the action outright)
        HIGH     → DENY  (same as critical; different audit severity)
        MEDIUM   → WARN  (allow but surface a warning)
        LOW      → ALLOW (log only)
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RiskTier(str, Enum):
    """Action risk classification for graduated responses."""

    LOW = "low"  # ≤ 30 risk score
    MEDIUM = "medium"  # 31-70
    HIGH = "high"  # > 70


@dataclass(frozen=True)
class ConstitutionalViolation:
    """A single policy violation detected by the auditor."""

    policy_id: str
    severity: PolicySeverity
    message: str
    # Optional extra context for audit logs
    check_name: Optional[str] = None


@dataclass
class AuditResult:
    """Outcome of a constitutional audit — used by callers to decide
    allow / warn / deny. Not frozen — callers may add metadata."""

    approved: bool
    decision: GovernanceDecision
    risk_tier: RiskTier
    risk_score: float  # 0..100
    violations: List[ConstitutionalViolation] = field(default_factory=list)
    rationale: str = ""


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
class IConstitutionalAuditor(Protocol):
    """Audits actions against a loaded constitution.

    Constitution is declarative (YAML), checks are deterministic
    (Python functions keyed by name in `check_function`). Auditor is
    stateless per audit call but may cache compiled regexes internally.

    Audit returns an `AuditResult` describing allow/warn/deny along with
    the specific policy violations. Callers translate the result into
    a `GovernanceDecision`.
    """

    def audit_stimulation(
        self,
        request: "StimulationRequest",
        system_state: Dict[str, Any],
    ) -> AuditResult:
        """Audit a stimulation request against the constitution."""
        ...

    def audit_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        agent: str,
        system_state: Dict[str, Any],
    ) -> AuditResult:
        """Audit a tool-call request against the constitution."""
        ...

    def to_dict(self) -> Dict[str, Any]:
        """Expose current constitution for snapshots."""
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


class NullConstitutionalAuditor:
    """No-op auditor: every action approved, empty violations list."""

    def audit_stimulation(
        self,
        request: "StimulationRequest",
        system_state: Dict[str, Any],
    ) -> AuditResult:
        return AuditResult(
            approved=True,
            decision=GovernanceDecision.ALLOW,
            risk_tier=RiskTier.LOW,
            risk_score=0.0,
            violations=[],
            rationale="null auditor",
        )

    def audit_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        agent: str,
        system_state: Dict[str, Any],
    ) -> AuditResult:
        return AuditResult(
            approved=True,
            decision=GovernanceDecision.ALLOW,
            risk_tier=RiskTier.LOW,
            risk_score=0.0,
            violations=[],
            rationale="null auditor",
        )

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "null", "policies": []}
