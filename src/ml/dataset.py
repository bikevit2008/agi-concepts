"""Build a (state, action, reward) dataset from the event store.

Used by offline-RL recovery policies. We treat the persisted event log
as a replay buffer:

    state:   features extracted from the snapshot event payload
             (runtime_state values + hysteresis channel values)
    action:  one of RecoveryAction enum values; "logged" actions come
             from `recovery_action` field of snapshot events
    reward:  user-defined reward function; default rewards proxy
             "channels stayed below 0.95" + "small action cost"

The output is a `RecoveryDataset` (numpy arrays) suitable for plug-in
into d3rlpy / pytorch / our minimal BC trainer.

For consciousness systems we don't have explicit rewards in the event
log (no environment-side reward signal). The dataset builder synthesizes
shaped rewards from observable outcomes (saturation avoidance,
hysteresis stability). This is a pragmatic MVP — production should
collect explicit reward labels.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import structlog

from src.contracts.ml import RecoveryAction
from src.contracts.persistence import EventRecord, IEventStore

logger = structlog.get_logger("consciousness.ml.dataset")


# Canonical action ordering — index ↔ enum
ACTION_ORDER: Tuple[RecoveryAction, ...] = (
    RecoveryAction.NONE,
    RecoveryAction.ALERT_ONLY,
    RecoveryAction.INJECT_CALM,
    RecoveryAction.LOWER_TEMPERATURE,
    RecoveryAction.RESET_CHANNEL,
    RecoveryAction.FORCE_SLEEP,
)
ACTION_TO_INDEX: Dict[RecoveryAction, int] = {a: i for i, a in enumerate(ACTION_ORDER)}
INDEX_TO_ACTION: Dict[int, RecoveryAction] = {i: a for i, a in enumerate(ACTION_ORDER)}


# Canonical feature ordering for state vector. Order is stable so the
# trained policy can be applied in production with the same layout.
FEATURE_KEYS: Tuple[str, ...] = (
    # runtime_state
    "rs.temperature",
    "rs.context_window",
    "rs.processing_latency",
    "rs.bandwidth",
    "rs.attention_focus",
    "rs.energy_level",
    # hysteresis channel values
    "ch.stress",
    "ch.euphoria",
    "ch.fatigue",
    "ch.pain",
)


def _extract_state(payload: Dict[str, Any]) -> Optional[List[float]]:
    """Project a snapshot payload into FEATURE_KEYS-ordered state vector."""
    rs = payload.get("runtime_state") or {}
    hyst = payload.get("hysteresis") or {}
    if not rs:
        return None

    def channel_value(name: str) -> float:
        ch = hyst.get(name) or {}
        if not isinstance(ch, dict):
            return 0.0
        try:
            return float(ch.get("value", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    try:
        # Normalise context_window to [0, 1] via /128_000 (max in clamp)
        cw = float(rs.get("context_window", 0) or 0) / 128_000.0
        return [
            float(rs.get("temperature", 0.0) or 0.0),
            cw,
            float(rs.get("processing_latency", 0.0) or 0.0),
            float(rs.get("bandwidth", 0.0) or 0.0),
            float(rs.get("attention_focus", 0.0) or 0.0),
            float(rs.get("energy_level", 0.0) or 0.0),
            channel_value("stress"),
            channel_value("euphoria"),
            channel_value("fatigue"),
            channel_value("pain"),
        ]
    except (TypeError, ValueError) as e:
        logger.warning("state_extract_failed", error=str(e))
        return None


def _action_from_payload(payload: Dict[str, Any]) -> Optional[RecoveryAction]:
    """Read a logged recovery_action from a snapshot payload, if any.

    Snapshot payloads from `_tick_inner` include `governance` /
    `circuit_breaker_tripped` etc. — we look at extension fields the
    loop appends when `flags.ml_regulators_enabled` is on
    (`ml_payload.recovery_action`). When absent → default to NONE so
    the dataset still includes idle ticks (useful for BC).
    """
    raw = payload.get("recovery_action")
    if raw is None:
        ml = payload.get("ml") or {}
        raw = ml.get("recovery_action")
    if raw is None:
        return RecoveryAction.NONE
    if isinstance(raw, RecoveryAction):
        return raw
    try:
        return RecoveryAction(str(raw))
    except ValueError:
        return None


def _default_reward(prev_state: List[float], next_state: List[float]) -> float:
    """Reward heuristic: penalise saturation, reward stability.

    Components:
      +1.0 if all hysteresis channel values < 0.95 in next_state
      -1.0 if any channel value ≥ 0.95
      +0.05 * energy_level   (encourage staying energetic)
      -0.10 if temperature > 1.5 (penalise chaos)
    """
    if not next_state or len(next_state) != len(FEATURE_KEYS):
        return 0.0
    # Channels are at indices 6..9
    ch = next_state[6:10]
    base = 1.0 if all(v < 0.95 for v in ch) else -1.0
    energy = next_state[5]
    temp = next_state[0]
    chaos_penalty = -0.1 if temp > 1.5 else 0.0
    return base + 0.05 * energy + chaos_penalty


@dataclass
class RecoveryDataset:
    """numpy-compatible dataset of (state, action, reward, next_state, done)."""

    states: List[List[float]]
    actions: List[int]
    rewards: List[float]
    next_states: List[List[float]]
    dones: List[bool]

    @property
    def n(self) -> int:
        return len(self.states)

    @property
    def feature_keys(self) -> Tuple[str, ...]:
        return FEATURE_KEYS

    @property
    def action_order(self) -> Tuple[RecoveryAction, ...]:
        return ACTION_ORDER

    def to_numpy(self):
        try:
            import numpy as np
        except ImportError as e:
            raise ImportError("numpy not available") from e
        return {
            "observations": np.asarray(self.states, dtype=float),
            "actions": np.asarray(self.actions, dtype=int),
            "rewards": np.asarray(self.rewards, dtype=float),
            "next_observations": np.asarray(self.next_states, dtype=float),
            "terminals": np.asarray(self.dones, dtype=bool),
        }


def build_dataset_from_event_store(
    event_store: IEventStore,
    reward_fn: Optional[Callable[[List[float], List[float]], float]] = None,
    max_records: Optional[int] = None,
) -> RecoveryDataset:
    """Stream snapshot events from the store and assemble (s, a, r, s', done)."""
    reward_fn = reward_fn or _default_reward

    states: List[List[float]] = []
    actions: List[int] = []
    rewards: List[float] = []
    next_states: List[List[float]] = []
    dones: List[bool] = []

    prev_state: Optional[List[float]] = None
    prev_action: Optional[int] = None
    count = 0
    for record in event_store.replay(event_type="snapshot"):
        state = _extract_state(record.payload)
        if state is None:
            continue
        action = _action_from_payload(record.payload)
        if action is None:
            continue
        if prev_state is not None and prev_action is not None:
            # The transition is from prev → current
            states.append(prev_state)
            actions.append(prev_action)
            rewards.append(reward_fn(prev_state, state))
            next_states.append(state)
            dones.append(False)
            count += 1
            if max_records is not None and count >= max_records:
                break
        prev_state = state
        prev_action = ACTION_TO_INDEX[action]

    if dones:
        # Mark the very last sample as done — episodic boundary
        dones[-1] = True

    logger.info("dataset_built", samples=count, feature_dim=len(FEATURE_KEYS))
    return RecoveryDataset(
        states=states,
        actions=actions,
        rewards=rewards,
        next_states=next_states,
        dones=dones,
    )


__all__ = [
    "ACTION_ORDER",
    "ACTION_TO_INDEX",
    "FEATURE_KEYS",
    "INDEX_TO_ACTION",
    "RecoveryDataset",
    "build_dataset_from_event_store",
]
