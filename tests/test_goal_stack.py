"""Tests for Stage 29 persistent intentions / goal stack."""

from __future__ import annotations

from pathlib import Path

from src.agents.base import PlanningResult, ReflectionResult
from src.config.flags import FeatureFlags
from src.config.settings import Settings
from src.contracts.goals import GoalStatus
from src.contracts.ml import (
    NullCollapseForecaster,
    NullRecoveryPolicy,
    NullRuminationDetector,
)
from src.contracts.observability import NullObservabilityCollector
from src.contracts.persistence import NullEventStore
from src.contracts.sleep import NullMemoryConsolidator, NullSleepManager
from src.core.consciousness_loop import ConsciousnessLoop
from src.core.event_bus import EventBus
from src.core.runtime_state import RuntimeState
from src.engine.circuit_breaker import SaturationCircuitBreaker
from src.engine.goal_stack import PersistentGoalStack
from src.engine.homeostatic_hysteresis import HomeostaticHysteresisEngine
from src.experiments.harness import ScriptedTeam, run_loop
from src.governance.kernel import DeterministicGovernanceKernel, GovernancePolicy
from src.persistence.sqlite_checkpoint import SqliteCheckpoint
from src.team.consciousness_team import ConsciousnessTeam


def test_goal_stack_orders_active_goals_and_deduplicates() -> None:
    stack = PersistentGoalStack(max_active_goals=2)

    low = stack.propose("Understand quiet curiosity", 0.2, tick=1, source="test")
    high = stack.propose("Maintain coherent self-model", 0.9, tick=2, source="test")
    duplicate = stack.propose(" understand quiet curiosity ", 0.8, tick=3, source="test")

    assert low is not None
    assert high is not None
    assert duplicate is None
    assert stack.top_active() == high
    assert [g.id for g in stack.active_goals()] == [high.id, low.id]


def test_goal_stack_refresh_blocks_stale_and_low_priority_under_pressure() -> None:
    stack = PersistentGoalStack(stale_after_ticks=5, pressure_stress_threshold=0.8)
    stale = stack.propose("Keep exploring silence", 0.9, tick=1)
    fragile = stack.propose("Optional low priority thought", 0.2, tick=9)

    assert stale is not None
    assert fragile is not None
    changed = stack.refresh(
        tick=10,
        runtime_state={},
        hysteresis_state={"stress": 0.85},
    )

    changed_ids = {g.id for g in changed}
    assert stale.id in changed_ids
    assert fragile.id in changed_ids
    assert stale.status == GoalStatus.BLOCKED
    assert fragile.status == GoalStatus.BLOCKED
    by_id = {goal["id"]: goal for goal in stack.to_dict()["goals"]}
    assert by_id[stale.id]["failure_count"] == 1
    assert by_id[fragile.id]["failure_count"] == 1


def test_goal_stack_serializes_and_restores() -> None:
    stack = PersistentGoalStack(stale_after_ticks=123)
    goal = stack.propose(
        "Remember this intention",
        0.7,
        tick=4,
        deadline_tick=42,
    )
    assert goal is not None
    stack.mark_progress(goal.id, tick=5, note="first step")

    restored = PersistentGoalStack()
    restored.restore(stack.to_dict())

    restored_goal = restored.top_active()
    assert restored_goal is not None
    assert restored_goal.id == goal.id
    assert restored_goal.deadline_tick == 42
    assert restored_goal.success_count == 1
    assert restored_goal.notes[-1].endswith("first step")
    assert restored.stale_after_ticks == 123


def test_team_reflection_can_propose_goal_without_llm_construction() -> None:
    stack = PersistentGoalStack()
    team = object.__new__(ConsciousnessTeam)
    team.flags = FeatureFlags()
    team.goal_stack = stack
    team.current_tick = 7

    team._maybe_propose_goal(
        ReflectionResult(
            thought="A durable curiosity emerged.",
            mood_assessment="curious",
            proposed_goal="Study why silence produces curiosity",
            goal_priority=0.8,
        )
    )

    goal = stack.top_active()
    assert goal is not None
    assert "silence" in goal.description
    assert goal.priority == 0.8


def test_team_planning_progress_updates_active_goal_without_llm_construction() -> None:
    stack = PersistentGoalStack()
    goal = stack.propose("Build a stable self-model", 0.7, tick=1)
    assert goal is not None

    team = object.__new__(ConsciousnessTeam)
    team.flags = FeatureFlags()
    team.goal_stack = stack
    team.current_tick = 2

    team._apply_goal_progress(
        PlanningResult(
            response="I will compare the current state to the goal.",
            intent="advance self-model",
            goal_progress="advanced",
            goal_progress_reason="used the goal as planning context",
        )
    )

    updated = stack.top_active()
    assert updated is not None
    assert updated.success_count == 1
    assert updated.last_pursued_tick == 2


def test_team_planning_progress_no_active_goal_is_noop() -> None:
    stack = PersistentGoalStack()
    team = object.__new__(ConsciousnessTeam)
    team.flags = FeatureFlags()
    team.goal_stack = stack
    team.current_tick = 2

    team._apply_goal_progress(
        PlanningResult(
            response="No active goal exists.",
            intent="noop",
            goal_progress="advanced",
        )
    )

    assert stack.to_dict()["goals"] == []


def test_team_planning_progress_disabled_is_noop() -> None:
    stack = PersistentGoalStack()
    goal = stack.propose("Do not update while disabled", 0.7, tick=1)
    assert goal is not None

    flags = FeatureFlags()
    flags.goal_stack_enabled = False
    team = object.__new__(ConsciousnessTeam)
    team.flags = flags
    team.goal_stack = stack
    team.current_tick = 2

    team._apply_goal_progress(
        PlanningResult(
            response="Would otherwise advance.",
            intent="noop",
            goal_progress="advanced",
        )
    )

    unchanged = stack.top_active()
    assert unchanged is not None
    assert unchanged.success_count == 0
    assert unchanged.last_pursued_tick == 1


def _build_loop_with_goal_checkpoint(tmp_path: Path, stack: PersistentGoalStack):
    settings = Settings()
    settings.persistence.checkpoint_path = str(tmp_path / "checkpoint.db")
    flags = FeatureFlags()
    flags.persistence_enabled = True
    flags.goal_stack_enabled = True

    runtime_state = RuntimeState()
    hysteresis = HomeostaticHysteresisEngine.from_settings(settings.hysteresis)
    team = ScriptedTeam(runtime_state=runtime_state, hysteresis=hysteresis)
    checkpoint = SqliteCheckpoint(settings.persistence.checkpoint_path)
    circuit_breaker = SaturationCircuitBreaker()
    governance = DeterministicGovernanceKernel(
        policy=GovernancePolicy(),
        circuit_breaker=circuit_breaker,
    )
    loop = ConsciousnessLoop(
        settings=settings,
        flags=flags,
        runtime_state=runtime_state,
        hysteresis=hysteresis,
        event_bus=EventBus(),
        team=team,
        governance=governance,
        circuit_breaker=circuit_breaker,
        event_store=NullEventStore(),
        checkpoint=checkpoint,
        observability=NullObservabilityCollector(),
        sleep_manager=NullSleepManager(),
        memory_consolidator=NullMemoryConsolidator(),
        rumination_detector=NullRuminationDetector(),
        collapse_forecaster=NullCollapseForecaster(),
        recovery_policy=NullRecoveryPolicy(),
        goal_stack=stack,
    )
    return loop, checkpoint


def test_checkpoint_restore_preserves_goal_stack(tmp_path: Path) -> None:
    stack = PersistentGoalStack()
    goal = stack.propose("Persist across restart", 0.9, tick=1)
    assert goal is not None

    loop, checkpoint = _build_loop_with_goal_checkpoint(tmp_path, stack)
    try:
        checkpoint.save(loop._build_snapshot())
    finally:
        checkpoint.close()

    restored_stack = PersistentGoalStack()
    loop2, checkpoint2 = _build_loop_with_goal_checkpoint(tmp_path, restored_stack)
    try:
        assert loop2.restore_from_checkpoint() is True
        restored_goal = restored_stack.top_active()
        assert restored_goal is not None
        assert restored_goal.id == goal.id
        assert restored_goal.description == "Persist across restart"
    finally:
        checkpoint2.close()


def test_harness_exposes_goal_stack_snapshot() -> None:
    result = run_loop(ticks=3, flags_overrides={"goal_stack_enabled": True})

    assert result.goal_stack["type"] == "persistent"
    assert result.goal_stack["goals"] == []
