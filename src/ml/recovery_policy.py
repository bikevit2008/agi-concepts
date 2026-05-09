"""Simple deterministic recovery policy.

Maps ML warnings to discrete actions:

    CRITICAL collapse (any channel) → FORCE_SLEEP
    CRITICAL rumination             → INJECT_CALM on stress channel
    WARNING collapse on stress      → INJECT_CALM on stress
    WARNING collapse on fatigue     → FORCE_SLEEP
    INFO-only                       → ALERT_ONLY (log, don't act)
    OK                              → NONE

This is intentionally simple. It's a baseline. A future version can
learn an RL policy over (state, warning) → action using the event log
as replay buffer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import structlog

from src.contracts.ml import (
    CollapseSignal,
    IRecoveryPolicy,
    RecoveryAction,
    RecoveryDecision,
    RuminationSignal,
    WarningLevel,
)

logger = structlog.get_logger("consciousness.ml.recovery")


def _most_severe(signals: List[CollapseSignal]) -> Optional[CollapseSignal]:
    severity_order = {
        WarningLevel.CRITICAL: 3,
        WarningLevel.WARNING: 2,
        WarningLevel.INFO: 1,
        WarningLevel.OK: 0,
    }
    if not signals:
        return None
    return max(signals, key=lambda s: severity_order.get(s.level, 0))


@dataclass
class RuleBasedRecoveryPolicy:
    """`IRecoveryPolicy` implementation with simple IF-THEN rules."""

    calm_intensity: float = 0.15  # negative stim magnitude on stress
    alert_on_info: bool = True

    def propose(
        self,
        rumination: Optional[RuminationSignal],
        collapse: List[CollapseSignal],
        runtime_state: Dict[str, float],
    ) -> RecoveryDecision:
        worst_collapse = _most_severe(collapse)

        # Rule 1: CRITICAL collapse → FORCE_SLEEP
        if worst_collapse and worst_collapse.level == WarningLevel.CRITICAL:
            return RecoveryDecision(
                action=RecoveryAction.FORCE_SLEEP,
                target=worst_collapse.channel,
                rationale=f"critical collapse on {worst_collapse.channel}",
            )

        # Rule 2: CRITICAL rumination → INJECT_CALM
        if rumination and rumination.level == WarningLevel.CRITICAL:
            return RecoveryDecision(
                action=RecoveryAction.INJECT_CALM,
                target="stress",
                intensity=self.calm_intensity,
                rationale=(
                    f"critical rumination (entropy={rumination.entropy:.3f}, "
                    f"dominant={rumination.dominant_state!r})"
                ),
            )

        # Rule 3: WARNING collapse on stress → INJECT_CALM
        if worst_collapse and worst_collapse.level == WarningLevel.WARNING:
            if worst_collapse.channel == "stress":
                return RecoveryDecision(
                    action=RecoveryAction.INJECT_CALM,
                    target="stress",
                    intensity=self.calm_intensity,
                    rationale=f"stress CSD warning ar1={worst_collapse.ar1:.2f}",
                )
            if worst_collapse.channel == "fatigue":
                return RecoveryDecision(
                    action=RecoveryAction.FORCE_SLEEP,
                    target=worst_collapse.channel,
                    rationale=f"fatigue CSD warning ar1={worst_collapse.ar1:.2f}",
                )

        # Rule 4: INFO-level anywhere → ALERT_ONLY
        if self.alert_on_info:
            any_info = (rumination and rumination.level == WarningLevel.INFO) or (
                worst_collapse and worst_collapse.level == WarningLevel.INFO
            )
            if any_info:
                return RecoveryDecision(
                    action=RecoveryAction.ALERT_ONLY,
                    rationale="info-level warning",
                )

        return RecoveryDecision(action=RecoveryAction.NONE, rationale="all OK")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "rule_based",
            "calm_intensity": self.calm_intensity,
            "alert_on_info": self.alert_on_info,
        }


# Statically assert the implementation satisfies the contract.
_: IRecoveryPolicy = RuleBasedRecoveryPolicy()


__all__ = ["RuleBasedRecoveryPolicy"]
