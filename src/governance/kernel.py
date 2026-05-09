"""Deterministic governance kernel — rate limiting + capability checks.

Implements `IGovernanceKernel`. Designed to be cheap (no LLM, no I/O)
so it can sit in the consciousness loop's hot path.

Policies enforced:
- per_tick_stimulus_cap: total |intensity| across all positive stimuli
  per tick. Prevents stimulation storms.
- per_agent_stimulus_cap: total |intensity| from a single agent per tick.
  Prevents one agent monopolising the budget.
- reflection_self_stim_cap: stricter cap on positive self-stimulation
  by the Reflection agent (V3 audit Bug #3).
- circuit_breaker_check: if a channel's circuit breaker is tripped, deny
  positive stimulation to that channel.

All caps apply to POSITIVE intensity only. Negative intensity (self-soothing,
relief, calming) is always allowed — denying it would be counterproductive
during recovery.

Reset semantics: per-tick counters reset on `begin_tick(tick)`.
FAIL-CLOSED: any unhandled error in authorize() returns DENY_PER_TICK_CAP.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import structlog

from src.contracts.governance import (
    AuditResult,
    GovernanceDecision,
    IConstitutionalAuditor,
    ICircuitBreaker,
    IGovernanceKernel,
    NullConstitutionalAuditor,
    StimulationRequest,
)

logger = structlog.get_logger("consciousness.governance")

# Float comparison tolerance — protects against IEEE-754 surprises
# (e.g. 0.1 + 0.1 + 0.1 == 0.30000000000000004 > 0.3 by a hair).
_FP_TOLERANCE = 1e-9


@dataclass
class GovernancePolicy:
    """Tunable policy parameters."""

    per_tick_stimulus_cap: float = 0.3
    per_agent_stimulus_cap: float = 0.2
    reflection_self_stim_cap: float = 0.1
    enforce_circuit_breaker: bool = True


@dataclass
class _TickStats:
    """Per-tick aggregations."""

    tick: int = -1
    total_positive: float = 0.0
    per_agent_positive: Dict[str, float] = field(default_factory=dict)
    per_channel_positive: Dict[str, float] = field(default_factory=dict)
    decisions: Dict[str, int] = field(default_factory=dict)


@dataclass
class DeterministicGovernanceKernel:
    """`IGovernanceKernel` implementation backed by deterministic counters.

    Construct with policy + an optional circuit breaker + an optional
    constitutional auditor. The kernel consults:
      1. the constitution (auditor) — WARN/DENY based on policy violations
      2. the circuit breaker
      3. the reflection/per-agent/per-tick caps
    """

    policy: GovernancePolicy = field(default_factory=GovernancePolicy)
    circuit_breaker: Optional[ICircuitBreaker] = None
    auditor: IConstitutionalAuditor = field(default_factory=NullConstitutionalAuditor)
    # Optional state provider; called each authorize() to get current
    # system state for constitution checks (e.g. cost_budget_exceeded).
    state_provider: Optional[Any] = None
    _stats: _TickStats = field(default_factory=_TickStats)
    _cumulative_decisions: Dict[str, int] = field(default_factory=dict)
    _last_audit: Optional[AuditResult] = None

    def begin_tick(self, tick: int) -> None:
        self._stats = _TickStats(tick=tick)

    def end_tick(self, tick: int) -> Dict[str, Any]:
        # Roll per-tick decisions into cumulative tracker
        for k, v in self._stats.decisions.items():
            self._cumulative_decisions[k] = self._cumulative_decisions.get(k, 0) + v
        return {
            "tick": self._stats.tick,
            "total_positive": round(self._stats.total_positive, 4),
            "per_agent": {k: round(v, 4) for k, v in self._stats.per_agent_positive.items()},
            "per_channel": {k: round(v, 4) for k, v in self._stats.per_channel_positive.items()},
            "decisions": dict(self._stats.decisions),
        }

    def authorize(self, request: StimulationRequest) -> GovernanceDecision:
        # Negative intensity always allowed — see module docstring.
        if request.intensity <= 0:
            return self._record_decision(GovernanceDecision.ALLOW)

        # Constitutional audit (runs first — strongest form of deny).
        # Stateless auditor; state provider is optional.
        try:
            state = self.state_provider() if callable(self.state_provider) else {}
        except Exception as e:
            logger.warning("state_provider_failed", error=str(e))
            state = {}
        audit = self.auditor.audit_stimulation(request, state)
        self._last_audit = audit
        if audit.decision == GovernanceDecision.DENY_CONSTITUTION:
            logger.warning(
                "governance_deny_constitution",
                agent=request.agent,
                channel=request.channel,
                rationale=audit.rationale,
                risk_tier=audit.risk_tier.value,
            )
            return self._record_decision(GovernanceDecision.DENY_CONSTITUTION)
        if audit.decision == GovernanceDecision.WARN_CONSTITUTION:
            logger.info(
                "governance_warn_constitution",
                agent=request.agent,
                channel=request.channel,
                rationale=audit.rationale,
            )
            # Continue to the remaining checks; WARN does not block.

        # Circuit breaker check
        if (
            self.policy.enforce_circuit_breaker
            and self.circuit_breaker is not None
            and self.circuit_breaker.is_tripped(request.channel)
        ):
            return self._record_decision(GovernanceDecision.DENY_CIRCUIT_BREAKER)

        # Reflection-specific cap
        if request.agent.lower() == "reflection":
            current = self._stats.per_agent_positive.get(request.agent, 0.0)
            if current + request.intensity > self.policy.reflection_self_stim_cap + _FP_TOLERANCE:
                logger.warning(
                    "governance_deny_reflection_cap",
                    agent=request.agent,
                    channel=request.channel,
                    intensity=request.intensity,
                    cap=self.policy.reflection_self_stim_cap,
                    current=current,
                )
                return self._record_decision(GovernanceDecision.DENY_REFLECTION_CAP)

        # Per-agent cap
        current_agent = self._stats.per_agent_positive.get(request.agent, 0.0)
        if current_agent + request.intensity > self.policy.per_agent_stimulus_cap + _FP_TOLERANCE:
            logger.info(
                "governance_deny_per_agent_cap",
                agent=request.agent,
                channel=request.channel,
                intensity=request.intensity,
                cap=self.policy.per_agent_stimulus_cap,
                current=current_agent,
            )
            return self._record_decision(GovernanceDecision.DENY_PER_AGENT_CAP)

        # Per-tick cap
        if self._stats.total_positive + request.intensity > self.policy.per_tick_stimulus_cap + _FP_TOLERANCE:
            logger.info(
                "governance_deny_per_tick_cap",
                agent=request.agent,
                channel=request.channel,
                intensity=request.intensity,
                cap=self.policy.per_tick_stimulus_cap,
                current=self._stats.total_positive,
            )
            return self._record_decision(GovernanceDecision.DENY_PER_TICK_CAP)

        return self._record_decision(GovernanceDecision.ALLOW)

    def record(self, request: StimulationRequest) -> None:
        # Negative intensity is allowed but we track it in stats too,
        # using absolute value for diagnostic purposes.
        amount = max(0.0, request.intensity)
        self._stats.total_positive += amount
        self._stats.per_agent_positive[request.agent] = (
            self._stats.per_agent_positive.get(request.agent, 0.0) + amount
        )
        self._stats.per_channel_positive[request.channel] = (
            self._stats.per_channel_positive.get(request.channel, 0.0) + amount
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "deterministic",
            "policy": {
                "per_tick_stimulus_cap": self.policy.per_tick_stimulus_cap,
                "per_agent_stimulus_cap": self.policy.per_agent_stimulus_cap,
                "reflection_self_stim_cap": self.policy.reflection_self_stim_cap,
                "enforce_circuit_breaker": self.policy.enforce_circuit_breaker,
            },
            "current_tick": {
                "tick": self._stats.tick,
                "total_positive": round(self._stats.total_positive, 4),
                "per_agent": {k: round(v, 4) for k, v in self._stats.per_agent_positive.items()},
                "per_channel": {k: round(v, 4) for k, v in self._stats.per_channel_positive.items()},
            },
            "cumulative_decisions": dict(self._cumulative_decisions),
            "auditor": self.auditor.to_dict(),
            "last_audit_rationale": (
                self._last_audit.rationale if self._last_audit else None
            ),
        }

    def _record_decision(self, decision: GovernanceDecision) -> GovernanceDecision:
        self._stats.decisions[decision.value] = self._stats.decisions.get(decision.value, 0) + 1
        return decision


# Statically assert the implementation satisfies the contract.
_: IGovernanceKernel = DeterministicGovernanceKernel()
