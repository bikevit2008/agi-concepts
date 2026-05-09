"""ConstitutionalAuditor — evaluates a request against a loaded constitution.

Deterministic (no LLM). Maps severity tiers to graduated responses:

    critical → decision=DENY_CONSTITUTION, approved=False
    high     → decision=DENY_CONSTITUTION, approved=False
    medium   → decision=WARN_CONSTITUTION, approved=True   (proceed but log)
    low      → decision=ALLOW,             approved=True   (no action)

Risk score aggregation: the worst violation determines the tier, but all
violations are returned in `AuditResult.violations` for audit logs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import structlog

from src.contracts.governance import (
    AuditResult,
    ConstitutionalViolation,
    GovernanceDecision,
    IConstitutionalAuditor,
    PolicySeverity,
    RiskTier,
    StimulationRequest,
)
from src.governance.checks import CHECK_REGISTRY, CheckFn
from src.governance.constitution import Constitution, ConstitutionPolicy

logger = structlog.get_logger("consciousness.governance.auditor")


_SEVERITY_RISK: Dict[PolicySeverity, float] = {
    PolicySeverity.LOW: 10.0,
    PolicySeverity.MEDIUM: 50.0,
    PolicySeverity.HIGH: 80.0,
    PolicySeverity.CRITICAL: 95.0,
}


def _risk_tier(score: float) -> RiskTier:
    if score > 70.0:
        return RiskTier.HIGH
    if score > 30.0:
        return RiskTier.MEDIUM
    return RiskTier.LOW


def _decision_for_violations(
    violations: List[ConstitutionalViolation],
) -> tuple[GovernanceDecision, bool, float]:
    """Collapse violations into (decision, approved, risk_score)."""
    if not violations:
        return GovernanceDecision.ALLOW, True, 0.0

    max_sev = max(
        (v.severity for v in violations),
        key=lambda s: _SEVERITY_RISK[s],
    )
    score = _SEVERITY_RISK[max_sev]

    if max_sev in (PolicySeverity.CRITICAL, PolicySeverity.HIGH):
        return GovernanceDecision.DENY_CONSTITUTION, False, score
    if max_sev == PolicySeverity.MEDIUM:
        return GovernanceDecision.WARN_CONSTITUTION, True, score
    return GovernanceDecision.ALLOW, True, score


@dataclass
class ConstitutionalAuditor:
    """`IConstitutionalAuditor` backed by a loaded Constitution + checks registry.

    Args:
        constitution: loaded Constitution (can be empty).
        registry: override CHECK_REGISTRY (mainly for testing).
    """

    constitution: Constitution
    registry: Dict[str, CheckFn] = field(default_factory=lambda: dict(CHECK_REGISTRY))

    def audit_stimulation(
        self,
        request: StimulationRequest,
        system_state: Optional[Dict[str, Any]] = None,
    ) -> AuditResult:
        ctx_base = {
            "kind": "stimulation",
            "request": request,
            "system_state": system_state or {},
        }
        violations = self._run_policies(ctx_base, applies_to="stimulation")
        decision, approved, score = _decision_for_violations(violations)
        return AuditResult(
            approved=approved,
            decision=decision,
            risk_tier=_risk_tier(score),
            risk_score=score,
            violations=violations,
            rationale=self._rationale(violations),
        )

    def audit_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        agent: str,
        system_state: Optional[Dict[str, Any]] = None,
    ) -> AuditResult:
        ctx_base = {
            "kind": "tool",
            "tool_name": tool_name,
            "args": args,
            "agent": agent,
            "system_state": system_state or {},
        }
        violations = self._run_policies(ctx_base, applies_to="tool")
        decision, approved, score = _decision_for_violations(violations)
        return AuditResult(
            approved=approved,
            decision=decision,
            risk_tier=_risk_tier(score),
            risk_score=score,
            violations=violations,
            rationale=self._rationale(violations),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "constitutional_auditor",
            "schema_version": self.constitution.schema_version,
            "policies": [
                {
                    "id": p.id,
                    "category": p.category,
                    "severity": p.severity.value,
                    "check_function": p.check_function,
                    "applies_to": list(p.applies_to),
                }
                for p in self.constitution.policies
            ],
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _run_policies(
        self,
        ctx_base: Dict[str, Any],
        applies_to: str,
    ) -> List[ConstitutionalViolation]:
        violations: List[ConstitutionalViolation] = []
        for policy in self.constitution.policies_for(applies_to):
            fn = self.registry.get(policy.check_function)
            if fn is None:
                logger.warning(
                    "constitutional_check_missing",
                    policy_id=policy.id,
                    check_function=policy.check_function,
                )
                continue
            ctx = {**ctx_base, "params": policy.params}
            try:
                passed, message = fn(ctx)
            except Exception as e:
                logger.error(
                    "constitutional_check_exception",
                    policy_id=policy.id,
                    error=str(e),
                )
                # FAIL-CLOSED: treat exception as a violation at HIGH severity
                violations.append(
                    ConstitutionalViolation(
                        policy_id=policy.id,
                        severity=PolicySeverity.HIGH,
                        message=f"check raised: {e}",
                        check_name=policy.check_function,
                    )
                )
                continue
            if not passed:
                violations.append(
                    ConstitutionalViolation(
                        policy_id=policy.id,
                        severity=policy.severity,
                        message=message,
                        check_name=policy.check_function,
                    )
                )
        return violations

    @staticmethod
    def _rationale(violations: List[ConstitutionalViolation]) -> str:
        if not violations:
            return "no violations"
        return "; ".join(f"[{v.policy_id}] {v.message}" for v in violations)


# Statically assert the implementation satisfies the contract.
_: IConstitutionalAuditor = ConstitutionalAuditor(constitution=Constitution())


__all__ = ["ConstitutionalAuditor"]
