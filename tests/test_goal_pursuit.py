"""Tests for Stage 30 active goal pursuit."""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.config.flags import FeatureFlags
from src.config.settings import Settings
from src.contracts.ml import (
    NullCollapseForecaster,
    NullRecoveryPolicy,
    NullRuminationDetector,
)
from src.contracts.observability import NullObservabilityCollector
from src.contracts.persistence import NullCheckpoint, NullEventStore
from src.contracts.sleep import NullMemoryConsolidator, NullSleepManager
from src.core.consciousness_loop import ConsciousnessLoop
from src.core.event_bus import EventBus
from src.core.runtime_state import RuntimeState
from src.engine.circuit_breaker import SaturationCircuitBreaker
from src.engine.goal_pursuit import DeterministicGoalPursuitPolicy
from src.engine.goal_stack import PersistentGoalStack
from src.engine.homeostatic_hysteresis import HomeostaticHysteresisEngine
from src.experiments.harness import ScriptedTeam
from src.governance.kernel import DeterministicGovernanceKernel, GovernancePolicy
from src.persistence.sqlite_checkpoint import SqliteCheckpoint


def test_goal_pursuit_waits_until_idle_and_stale() -> None:
    stack = PersistentGoalStack()
    goal = stack.propose("Understand recurring curiosity", 0.8, tick=1)
    assert goal is not None
    policy = DeterministicGoalPursuitPolicy(
        min_idle_ticks=2,
        progress_stale_after_ticks=4,
    )

    early = policy.maybe_pursue(
        tick=3,
        idle_ticks=2,
        goal=goal,
        runtime_state={},
        hysteresis_state={},
    )
    ready = policy.maybe_pursue(
        tick=5,
        idle_ticks=2,
        goal=goal,
        runtime_state={},
        hysteresis_state={},
    )

    assert early is None
    assert ready is not None
    assert ready.stimulus.startswith(f"[goal:{goal.id}]")
    assert "Understand recurring curiosity" in ready.stimulus


def test_goal_pursuit_rate_limits_repeated_attempts() -> None:
    stack = PersistentGoalStack()
    goal = stack.propose("Keep one stable intention", 0.8, tick=1)
    assert goal is not None
    policy = DeterministicGoalPursuitPolicy(
        min_idle_ticks=1,
        min_ticks_between_attempts=10,
        progress_stale_after_ticks=1,
    )

    first = policy.maybe_pursue(3, 3, goal, {}, {})
    assert first is not None
    policy.record(first)

    blocked = policy.maybe_pursue(8, 8, goal, {}, {})
    allowed = policy.maybe_pursue(13, 13, goal, {}, {})

    assert blocked is None
    assert allowed is not None


def test_goal_pursuit_pauses_low_priority_goals_under_high_stress() -> None:
    stack = PersistentGoalStack()
    goal = stack.propose("Optional side exploration", 0.2, tick=1)
    assert goal is not None
    policy = DeterministicGoalPursuitPolicy(
        min_idle_ticks=1,
        progress_stale_after_ticks=1,
        pause_stress_threshold=0.8,
        pause_low_priority_below=0.5,
    )

    decision = policy.maybe_pursue(
        tick=3,
        idle_ticks=3,
        goal=goal,
        runtime_state={},
        hysteresis_state={"stress": 0.9},
    )

    assert decision is None


def test_goal_pursuit_restore_preserves_attempt_counters() -> None:
    stack = PersistentGoalStack()
    goal = stack.propose("Restore pursuit counters", 0.8, tick=1)
    assert goal is not None
    policy = DeterministicGoalPursuitPolicy(
        min_idle_ticks=1,
        min_ticks_between_attempts=10,
        progress_stale_after_ticks=1,
    )
    decision = policy.maybe_pursue(3, 3, goal, {}, {})
    assert decision is not None
    policy.record(decision)

    restored = DeterministicGoalPursuitPolicy()
    restored.restore(policy.to_dict())

    assert restored.to_dict()["attempts_by_goal"][goal.id] == 1
    assert restored.maybe_pursue(8, 8, goal, {}, {}) is None


def _build_goal_pursuit_loop(
    tmp_path: Path | None = None,
    persist: bool = False,
) -> tuple[ConsciousnessLoop, ScriptedTeam, PersistentGoalStack]:
    settings = Settings()
    if tmp_path is not None:
        settings.persistence.checkpoint_path = str(tmp_path / "checkpoint.db")
    flags = FeatureFlags()
    flags.persistence_enabled = persist
    flags.goal_stack_enabled = True
    flags.goal_pursuit_enabled = True
    flags.self_reflection_enabled = False
    flags.autonomous_thoughts_enabled = False

    runtime_state = RuntimeState()
    hysteresis = HomeostaticHysteresisEngine.from_settings(settings.hysteresis)
    processed: list[str] = []
    team = ScriptedTeam(
        runtime_state=runtime_state,
        hysteresis=hysteresis,
        stimulus_response=lambda s: processed.append(s) or {"response": s},
    )
    team.processed_stimuli = processed  # dynamic test-only probe

    goal_stack = PersistentGoalStack()
    goal_stack.propose("Actively inspect the quiet goal", 0.8, tick=0)
    goal_pursuit = DeterministicGoalPursuitPolicy(
        min_idle_ticks=1,
        min_ticks_between_attempts=10,
        progress_stale_after_ticks=2,
    )
    circuit_breaker = SaturationCircuitBreaker()
    checkpoint = (
        SqliteCheckpoint(settings.persistence.checkpoint_path)
        if persist
        else None
    )
    loop = ConsciousnessLoop(
        settings=settings,
        flags=flags,
        runtime_state=runtime_state,
        hysteresis=hysteresis,
        event_bus=EventBus(),
        team=team,
        governance=DeterministicGovernanceKernel(
            policy=GovernancePolicy(),
            circuit_breaker=circuit_breaker,
        ),
        circuit_breaker=circuit_breaker,
        event_store=NullEventStore(),
        checkpoint=checkpoint or NullCheckpoint(),
        observability=NullObservabilityCollector(),
        sleep_manager=NullSleepManager(),
        memory_consolidator=NullMemoryConsolidator(),
        rumination_detector=NullRuminationDetector(),
        collapse_forecaster=NullCollapseForecaster(),
        recovery_policy=NullRecoveryPolicy(),
        goal_stack=goal_stack,
        goal_pursuit_policy=goal_pursuit,
    )
    return loop, team, goal_stack


def test_loop_enqueues_and_processes_goal_pursuit_stimulus() -> None:
    loop, team, _ = _build_goal_pursuit_loop()
    try:
        loop._simulated_dt = loop.settings.consciousness_loop.tick_interval_sec

        async def drive() -> None:
            for _ in range(3):
                await loop._tick()

        asyncio.run(drive())

        assert getattr(team, "processed_stimuli")
        assert getattr(team, "processed_stimuli")[0].startswith("[goal:")
        assert loop.goal_pursuit_policy.to_dict()["attempts_by_goal"]
    finally:
        loop.checkpoint.close()


def test_loop_goal_pursuit_resets_idle_ticks_only_when_processed() -> None:
    loop, team, _ = _build_goal_pursuit_loop()
    try:
        loop._simulated_dt = loop.settings.consciousness_loop.tick_interval_sec

        async def drive() -> None:
            await loop._tick()
            assert loop._idle_ticks == 1
            assert loop._stimulus_queue.qsize() == 0

            await loop._tick()
            assert loop._idle_ticks == 2
            assert loop._stimulus_queue.qsize() == 1
            assert getattr(team, "processed_stimuli") == []

            await loop._tick()
            assert loop._idle_ticks == 0

        asyncio.run(drive())

        assert getattr(team, "processed_stimuli")
        assert getattr(team, "processed_stimuli")[0].startswith("[goal:")
    finally:
        loop.checkpoint.close()


def test_loop_goal_pursuit_respects_disabled_flag() -> None:
    loop, team, _ = _build_goal_pursuit_loop()
    loop.flags.goal_pursuit_enabled = False
    try:
        loop._simulated_dt = loop.settings.consciousness_loop.tick_interval_sec

        async def drive() -> None:
            for _ in range(4):
                await loop._tick()

        asyncio.run(drive())

        assert getattr(team, "processed_stimuli") == []
        assert loop.goal_pursuit_policy.to_dict()["attempts_by_goal"] == {}
    finally:
        loop.checkpoint.close()


def test_loop_goal_pursuit_can_be_enabled_after_start_disabled() -> None:
    loop, team, _ = _build_goal_pursuit_loop()
    loop.flags.goal_pursuit_enabled = False
    try:
        loop._simulated_dt = loop.settings.consciousness_loop.tick_interval_sec

        async def drive() -> None:
            for _ in range(4):
                await loop._tick()
            assert getattr(team, "processed_stimuli") == []

            loop.flags.goal_pursuit_enabled = True
            for _ in range(2):
                await loop._tick()

        asyncio.run(drive())

        assert getattr(team, "processed_stimuli")
        assert loop.goal_pursuit_policy.to_dict()["attempts_by_goal"]
    finally:
        loop.checkpoint.close()


def test_checkpoint_restore_preserves_goal_pursuit_policy(tmp_path: Path) -> None:
    loop, _, goal_stack = _build_goal_pursuit_loop(tmp_path=tmp_path, persist=True)
    goal = goal_stack.top_active()
    assert goal is not None
    try:
        decision = loop.goal_pursuit_policy.maybe_pursue(3, 3, goal, {}, {})
        assert decision is not None
        loop.goal_pursuit_policy.record(decision)
        loop.checkpoint.save(loop._build_snapshot())
    finally:
        loop.checkpoint.close()

    restored_loop, _, _ = _build_goal_pursuit_loop(tmp_path=tmp_path, persist=True)
    try:
        assert restored_loop.restore_from_checkpoint() is True
        state = restored_loop.goal_pursuit_policy.to_dict()
        assert state["attempts_by_goal"][goal.id] == 1
    finally:
        restored_loop.checkpoint.close()
