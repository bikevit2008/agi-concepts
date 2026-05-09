"""Offline-RL recovery policy via Behavior Cloning.

Trains a multinomial logistic-regression-style classifier
(state → action) using existing event-log transitions. At inference
time, feeds current `runtime_state + hysteresis` as features into the
trained weights to pick an action.

Why BC and not CQL/IQL right now:

- BC needs only numpy + small dataset. CQL/IQL would pull in PyTorch
  / d3rlpy and a meaningful state distribution shift estimator, which
  is overkill for an MVP with a couple hundred logged transitions.
- BC is a strong baseline for "imitate what the rule-based policy
  has done historically" — it generalises across slight state
  variations. We swap to CQL once we have richer reward signals
  and ≥10k transitions per `dify-search` SOTA 2026.

Hybrid mode: if the trained policy's max-class probability falls below
`confidence_threshold`, fall back to the rule-based policy. This means
we never propose an action with low certainty — the system stays
conservative.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog

from src.contracts.ml import (
    CollapseSignal,
    IRecoveryPolicy,
    RecoveryAction,
    RecoveryDecision,
    RuminationSignal,
)
from src.ml.dataset import (
    ACTION_ORDER,
    ACTION_TO_INDEX,
    FEATURE_KEYS,
    INDEX_TO_ACTION,
    RecoveryDataset,
)
from src.ml.recovery_policy import RuleBasedRecoveryPolicy

logger = structlog.get_logger("consciousness.ml.offline_recovery")


def _softmax(xs: List[float]) -> List[float]:
    if not xs:
        return []
    m = max(xs)
    exps = [math.exp(x - m) for x in xs]
    s = sum(exps)
    if s == 0:
        return [1.0 / len(xs)] * len(xs)
    return [e / s for e in exps]


@dataclass
class BehaviorCloningPolicy:
    """Multinomial logistic regression trained via batch gradient descent.

    Parameters W and b are stored as plain Python lists for portability
    (no numpy required at inference time).
    """

    W: List[List[float]] = field(default_factory=list)  # shape: (n_actions, n_features)
    b: List[float] = field(default_factory=list)        # shape: (n_actions,)
    n_features: int = 0
    n_actions: int = 0
    feature_keys: Tuple[str, ...] = FEATURE_KEYS

    def predict_proba(self, state: List[float]) -> List[float]:
        if self.n_actions == 0 or not self.W:
            return []
        logits = []
        for a in range(self.n_actions):
            s = self.b[a]
            row = self.W[a]
            for i, x in enumerate(state):
                if i >= len(row):
                    break
                s += row[i] * x
            logits.append(s)
        return _softmax(logits)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "bc",
            "n_features": self.n_features,
            "n_actions": self.n_actions,
            "feature_keys": list(self.feature_keys),
            "W": self.W,
            "b": self.b,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BehaviorCloningPolicy":
        return cls(
            W=data.get("W") or [],
            b=data.get("b") or [],
            n_features=int(data.get("n_features") or 0),
            n_actions=int(data.get("n_actions") or 0),
            feature_keys=tuple(data.get("feature_keys") or FEATURE_KEYS),
        )


def train_bc(
    dataset: RecoveryDataset,
    n_epochs: int = 100,
    learning_rate: float = 0.05,
    l2: float = 1e-3,
) -> BehaviorCloningPolicy:
    """Train a multinomial logistic regression on the dataset.

    Pure numpy. Small enough that pure-Python would also work for tiny
    datasets, but numpy is already a dependency.
    """
    try:
        import numpy as np
    except ImportError as e:
        raise ImportError("numpy required to train BC policy") from e

    if dataset.n == 0:
        return BehaviorCloningPolicy(n_features=len(FEATURE_KEYS), n_actions=len(ACTION_ORDER))

    X = np.asarray(dataset.states, dtype=float)
    y = np.asarray(dataset.actions, dtype=int)
    n_features = X.shape[1]
    n_actions = len(ACTION_ORDER)

    # one-hot
    Y = np.zeros((X.shape[0], n_actions), dtype=float)
    Y[np.arange(X.shape[0]), y] = 1.0

    rng = np.random.default_rng(seed=42)
    W = rng.standard_normal((n_actions, n_features)) * 0.01
    b = np.zeros(n_actions)

    for epoch in range(n_epochs):
        logits = X @ W.T + b  # (N, A)
        max_logits = logits.max(axis=1, keepdims=True)
        exp_l = np.exp(logits - max_logits)
        probs = exp_l / exp_l.sum(axis=1, keepdims=True)

        # Gradient w.r.t. cross-entropy
        diff = probs - Y  # (N, A)
        grad_W = diff.T @ X / X.shape[0] + l2 * W
        grad_b = diff.sum(axis=0) / X.shape[0]

        W -= learning_rate * grad_W
        b -= learning_rate * grad_b

    return BehaviorCloningPolicy(
        W=W.tolist(),
        b=b.tolist(),
        n_features=int(n_features),
        n_actions=int(n_actions),
    )


@dataclass
class OfflineRecoveryPolicy:
    """`IRecoveryPolicy` that uses a trained BC policy with rule-based fallback.

    Behavior:
      - If the trained policy's top-class probability ≥ confidence_threshold,
        propose that action.
      - Otherwise (or if no trained policy yet), defer to the rule-based
        policy.

    This keeps the system safe — we never roll out an unfamiliar action
    when the model isn't sure.
    """

    bc_policy: Optional[BehaviorCloningPolicy] = None
    fallback: IRecoveryPolicy = field(default_factory=RuleBasedRecoveryPolicy)
    confidence_threshold: float = 0.6
    calm_intensity: float = 0.15

    def propose(
        self,
        rumination: Optional[RuminationSignal],
        collapse: List[CollapseSignal],
        runtime_state: Dict[str, float],
    ) -> RecoveryDecision:
        if self.bc_policy is None or self.bc_policy.n_actions == 0:
            return self.fallback.propose(rumination, collapse, runtime_state)

        state = self._build_state_vector(runtime_state, collapse)
        try:
            probs = self.bc_policy.predict_proba(state)
        except Exception as e:
            logger.warning("bc_predict_failed", error=str(e))
            return self.fallback.propose(rumination, collapse, runtime_state)

        if not probs:
            return self.fallback.propose(rumination, collapse, runtime_state)

        top_idx = int(max(range(len(probs)), key=lambda i: probs[i]))
        top_p = probs[top_idx]
        if top_p < self.confidence_threshold:
            decision = self.fallback.propose(rumination, collapse, runtime_state)
            return RecoveryDecision(
                action=decision.action,
                target=decision.target,
                intensity=decision.intensity,
                rationale=f"bc_unsure({top_p:.2f}); fallback: {decision.rationale}",
            )

        action = INDEX_TO_ACTION.get(top_idx, RecoveryAction.NONE)
        target, intensity = self._defaults_for(action, collapse)
        return RecoveryDecision(
            action=action,
            target=target,
            intensity=intensity,
            rationale=f"bc(p={top_p:.2f})",
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "offline_bc",
            "confidence_threshold": self.confidence_threshold,
            "trained": self.bc_policy is not None,
            "n_actions": self.bc_policy.n_actions if self.bc_policy else 0,
            "fallback": getattr(self.fallback, "to_dict", lambda: {})(),
        }

    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        """Persist the trained BC policy to disk as JSON."""
        if self.bc_policy is None:
            return
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.bc_policy.to_dict(), f)

    @classmethod
    def load(
        cls,
        path: str | Path,
        fallback: Optional[IRecoveryPolicy] = None,
    ) -> "OfflineRecoveryPolicy":
        """Load a previously-trained BC policy from disk."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(
            bc_policy=BehaviorCloningPolicy.from_dict(data),
            fallback=fallback or RuleBasedRecoveryPolicy(),
        )

    # ------------------------------------------------------------------

    def _build_state_vector(
        self,
        runtime_state: Dict[str, float],
        collapse: List[CollapseSignal],
    ) -> List[float]:
        """Project current state to FEATURE_KEYS vector."""
        rs = runtime_state or {}
        ch_values: Dict[str, float] = {}
        for sig in collapse or []:
            ch_values[sig.channel] = float(getattr(sig, "ar1", 0.0) or 0.0) * 0 + 0.0
        # Hysteresis values come from runtime_state too if loop populates them;
        # but our `runtime_state` arg from IRecoveryPolicy may not include them.
        # The training-time feature builder used snapshot payloads, so at
        # inference we reconstruct as best we can.
        cw = float(rs.get("context_window", 0) or 0) / 128_000.0
        return [
            float(rs.get("temperature", 0.0) or 0.0),
            cw,
            float(rs.get("processing_latency", 0.0) or 0.0),
            float(rs.get("bandwidth", 0.0) or 0.0),
            float(rs.get("attention_focus", 0.0) or 0.0),
            float(rs.get("energy_level", 0.0) or 0.0),
            ch_values.get("stress", 0.0),
            ch_values.get("euphoria", 0.0),
            ch_values.get("fatigue", 0.0),
            ch_values.get("pain", 0.0),
        ]

    def _defaults_for(
        self, action: RecoveryAction, collapse: List[CollapseSignal]
    ) -> Tuple[Optional[str], float]:
        if action == RecoveryAction.INJECT_CALM:
            return ("stress", self.calm_intensity)
        if action == RecoveryAction.FORCE_SLEEP:
            target = None
            if collapse:
                target = collapse[0].channel
            return (target, 0.0)
        if action == RecoveryAction.RESET_CHANNEL:
            target = collapse[0].channel if collapse else None
            return (target, 0.0)
        return (None, 0.0)


__all__ = [
    "BehaviorCloningPolicy",
    "OfflineRecoveryPolicy",
    "train_bc",
]
