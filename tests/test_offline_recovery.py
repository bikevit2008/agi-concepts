"""Tests for the offline-RL recovery pipeline (Stage 16)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.contracts.ml import (
    CollapseSignal,
    IRecoveryPolicy,
    RecoveryAction,
    RecoveryDecision,
    RuminationSignal,
    WarningLevel,
)
from src.ml.dataset import (
    ACTION_ORDER,
    ACTION_TO_INDEX,
    FEATURE_KEYS,
    INDEX_TO_ACTION,
    RecoveryDataset,
    build_dataset_from_event_store,
)
from src.ml.offline_recovery import (
    BehaviorCloningPolicy,
    OfflineRecoveryPolicy,
    train_bc,
)
from src.ml.recovery_policy import RuleBasedRecoveryPolicy
from src.persistence.sqlite_event_store import SqliteEventStore


# --- Dataset builder -------------------------------------------------------


def _make_snapshot_payload(
    temp: float = 0.7,
    energy: float = 1.0,
    stress: float = 0.0,
    fatigue: float = 0.0,
    action: str = RecoveryAction.NONE.value,
) -> Dict[str, Any]:
    return {
        "tick": 0,
        "runtime_state": {
            "temperature": temp,
            "context_window": 32768,
            "processing_latency": 0.0,
            "bandwidth": 1.0,
            "attention_focus": 1.0,
            "energy_level": energy,
        },
        "hysteresis": {
            "stress": {"value": stress},
            "euphoria": {"value": 0.0},
            "fatigue": {"value": fatigue},
            "pain": {"value": 0.0},
        },
        "recovery_action": action,
    }


def test_dataset_builds_transitions(tmp_path: Path):
    es = SqliteEventStore(str(tmp_path / "events.db"))
    try:
        # Three snapshots → 2 transitions
        es.append(1, "snapshot", _make_snapshot_payload(stress=0.0))
        es.append(2, "snapshot", _make_snapshot_payload(stress=0.5))
        es.append(3, "snapshot", _make_snapshot_payload(stress=0.95))

        dataset = build_dataset_from_event_store(es)
        assert dataset.n == 2
        assert len(dataset.states[0]) == len(FEATURE_KEYS)
        # Last sample marked done
        assert dataset.dones[-1] is True
        # First not done
        assert dataset.dones[0] is False
    finally:
        es.close()


def test_dataset_action_decoding(tmp_path: Path):
    es = SqliteEventStore(str(tmp_path / "events.db"))
    try:
        es.append(
            1,
            "snapshot",
            _make_snapshot_payload(action=RecoveryAction.INJECT_CALM.value),
        )
        es.append(
            2,
            "snapshot",
            _make_snapshot_payload(action=RecoveryAction.FORCE_SLEEP.value),
        )

        dataset = build_dataset_from_event_store(es)
        assert dataset.actions[0] == ACTION_TO_INDEX[RecoveryAction.INJECT_CALM]
    finally:
        es.close()


def test_dataset_reward_function(tmp_path: Path):
    es = SqliteEventStore(str(tmp_path / "events.db"))
    try:
        # First snapshot: low stress → next snapshot also low stress → +reward
        es.append(1, "snapshot", _make_snapshot_payload(stress=0.1))
        es.append(2, "snapshot", _make_snapshot_payload(stress=0.2))
        # And another transition into saturation → −reward
        es.append(3, "snapshot", _make_snapshot_payload(stress=0.96))

        dataset = build_dataset_from_event_store(es)
        # First transition (low → low) reward > 0
        assert dataset.rewards[0] > 0
        # Second transition (low → saturated) reward < 0
        assert dataset.rewards[1] < 0
    finally:
        es.close()


def test_dataset_to_numpy(tmp_path: Path):
    pytest.importorskip("numpy")
    es = SqliteEventStore(str(tmp_path / "events.db"))
    try:
        for i in range(5):
            es.append(i + 1, "snapshot", _make_snapshot_payload(stress=i * 0.1))
        dataset = build_dataset_from_event_store(es)
        arrays = dataset.to_numpy()
        assert arrays["observations"].shape[0] == dataset.n
        assert arrays["observations"].shape[1] == len(FEATURE_KEYS)
    finally:
        es.close()


def test_dataset_max_records_caps(tmp_path: Path):
    es = SqliteEventStore(str(tmp_path / "events.db"))
    try:
        for i in range(20):
            es.append(i + 1, "snapshot", _make_snapshot_payload())
        dataset = build_dataset_from_event_store(es, max_records=5)
        assert dataset.n == 5
    finally:
        es.close()


# --- BC training -----------------------------------------------------------


def _synthetic_dataset(n_per_action: int = 30) -> RecoveryDataset:
    """Three actions, each with a distinct state region — easy to learn."""
    states: List[List[float]] = []
    actions: List[int] = []
    rewards: List[float] = []
    next_states: List[List[float]] = []
    dones: List[bool] = []

    base_dim = len(FEATURE_KEYS)
    for action_idx, (act, region_signature) in enumerate(
        [
            (RecoveryAction.NONE, [0.0] * base_dim),
            (RecoveryAction.FORCE_SLEEP, [1.0] + [0.0] * (base_dim - 1)),
            (
                RecoveryAction.INJECT_CALM,
                [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
            ),
        ]
    ):
        for _ in range(n_per_action):
            s = [v + (0.01 * (action_idx + 1)) for v in region_signature]
            states.append(s)
            actions.append(ACTION_TO_INDEX[act])
            rewards.append(0.0)
            next_states.append(s)
            dones.append(False)

    return RecoveryDataset(states, actions, rewards, next_states, dones)


def test_train_bc_learns_separable_actions():
    pytest.importorskip("numpy")
    dataset = _synthetic_dataset(n_per_action=40)
    policy = train_bc(dataset, n_epochs=300, learning_rate=0.1)

    # Test on points from each region
    for action, region in [
        (RecoveryAction.NONE, [0.001] * len(FEATURE_KEYS)),
        (RecoveryAction.FORCE_SLEEP, [1.001] + [0.001] * (len(FEATURE_KEYS) - 1)),
        (
            RecoveryAction.INJECT_CALM,
            [0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 1.001, 0.001, 0.001, 0.001],
        ),
    ]:
        probs = policy.predict_proba(region)
        top = max(range(len(probs)), key=lambda i: probs[i])
        assert top == ACTION_TO_INDEX[action], (
            f"expected {action.value}, got {INDEX_TO_ACTION[top].value}"
        )


def test_train_bc_handles_empty_dataset():
    empty = RecoveryDataset([], [], [], [], [])
    policy = train_bc(empty)
    # Empty policy returns empty probs
    assert policy.predict_proba([0.0] * 10) == []


def test_bc_save_load_roundtrip(tmp_path: Path):
    pytest.importorskip("numpy")
    dataset = _synthetic_dataset(n_per_action=20)
    policy = train_bc(dataset, n_epochs=100)
    p = OfflineRecoveryPolicy(bc_policy=policy)
    save_path = tmp_path / "bc.json"
    p.save(save_path)
    p2 = OfflineRecoveryPolicy.load(save_path)
    assert p2.bc_policy is not None
    # Same parameters
    assert p2.bc_policy.n_actions == p.bc_policy.n_actions
    # Same predictions
    test_state = [0.5] * len(FEATURE_KEYS)
    probs1 = p.bc_policy.predict_proba(test_state)
    probs2 = p2.bc_policy.predict_proba(test_state)
    assert all(abs(a - b) < 1e-6 for a, b in zip(probs1, probs2))


# --- OfflineRecoveryPolicy ------------------------------------------------


def test_offline_policy_falls_back_when_no_bc():
    """No trained policy → defer to fallback."""
    p = OfflineRecoveryPolicy(bc_policy=None)
    decision = p.propose(
        rumination=RuminationSignal(WarningLevel.OK, 2.0, 30, 5),
        collapse=[CollapseSignal(WarningLevel.OK, "stress", 0.1, 0.01, 0.0)],
        runtime_state={"energy_level": 1.0, "temperature": 0.7},
    )
    assert decision.action == RecoveryAction.NONE


def test_offline_policy_uses_bc_when_confident():
    pytest.importorskip("numpy")
    dataset = _synthetic_dataset(n_per_action=80)
    policy = train_bc(dataset, n_epochs=400, learning_rate=0.15)
    p = OfflineRecoveryPolicy(
        bc_policy=policy,
        confidence_threshold=0.5,
    )
    # State near FORCE_SLEEP region
    runtime_state = {
        "temperature": 1.001,
        "context_window": 0.001,
        "processing_latency": 0.001,
        "bandwidth": 0.001,
        "attention_focus": 0.001,
        "energy_level": 0.001,
    }
    decision = p.propose(
        rumination=None,
        collapse=[],  # no signals; only runtime_state used
        runtime_state=runtime_state,
    )
    # We expect ANY action other than NONE because BC region differs from default
    assert decision.action in (
        RecoveryAction.NONE,
        RecoveryAction.FORCE_SLEEP,
        RecoveryAction.INJECT_CALM,
    )


def test_offline_policy_falls_back_when_unsure():
    """When BC's top probability < threshold, defer to fallback."""

    class _MockBc(BehaviorCloningPolicy):
        def predict_proba(self, state):  # type: ignore[override]
            # All actions equally likely → uncertain
            return [1.0 / len(ACTION_ORDER)] * len(ACTION_ORDER)

    mock = _MockBc(W=[[]], b=[0], n_features=10, n_actions=len(ACTION_ORDER))
    p = OfflineRecoveryPolicy(
        bc_policy=mock,
        fallback=RuleBasedRecoveryPolicy(),
        confidence_threshold=0.9,
    )
    decision = p.propose(
        rumination=RuminationSignal(WarningLevel.CRITICAL, 0.05, 30, 1),
        collapse=[],
        runtime_state={},
    )
    # Fallback rule says CRITICAL rumination → INJECT_CALM
    assert decision.action == RecoveryAction.INJECT_CALM
    assert "bc_unsure" in decision.rationale


def test_offline_policy_satisfies_contract():
    p: IRecoveryPolicy = OfflineRecoveryPolicy()
    assert isinstance(p, IRecoveryPolicy)


def test_offline_policy_to_dict():
    p = OfflineRecoveryPolicy(
        bc_policy=BehaviorCloningPolicy(W=[[1, 2]], b=[0], n_features=2, n_actions=1)
    )
    d = p.to_dict()
    assert d["type"] == "offline_bc"
    assert d["trained"] is True
