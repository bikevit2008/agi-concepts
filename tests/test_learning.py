"""Tests for Stage 32 lightweight self-learning context."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

from src.bus.asyncio_bus import AsyncioEventBus
from src.bus.event_types import EventTypes
from src.config.flags import FeatureFlags
from src.config.settings import Settings
from src.contracts.governance import NullCircuitBreaker, NullGovernanceKernel
from src.contracts.goals import NullGoalStack
from src.contracts.learning import NullLearningStore
from src.contracts.memory import NullMemoryStore
from src.contracts.observability import NullObservabilityCollector
from src.contracts.persistence import NullEventStore
from src.contracts.sleep import NullMemoryConsolidator, NullSleepManager
from src.core.consciousness_loop import ConsciousnessLoop
from src.core.runtime_state import RuntimeState
from src.engine.homeostatic_hysteresis import HomeostaticHysteresisEngine
from src.engine.learning_store import PersistentLearningStore
from src.experiments.harness import LoopHarness, ScriptedTeam, run_loop
from src.persistence.sqlite_checkpoint import SqliteCheckpoint
from src.team.consciousness_team import ConsciousnessTeam


def test_learning_store_records_session_context_and_limits_events() -> None:
    store = PersistentLearningStore(max_recent_events=2)

    for tick, stimulus in enumerate(["first", "second", "third"], start=1):
        store.record_interaction(
            tick=tick,
            stimulus=stimulus,
            result={
                "response": f"response:{stimulus}",
                "planning": {
                    "intent": f"intent:{stimulus}",
                    "next_actions": ["inspect", "answer"],
                    "goal_progress": "advanced",
                    "goal_progress_reason": "made a bounded step",
                },
            },
            current_goal={"description": "Maintain coherent self-learning"},
        )

    ctx = store.session_context
    assert ctx.interaction_count == 3
    assert ctx.updated_tick == 3
    assert ctx.current_goal == "Maintain coherent self-learning"
    assert ctx.current_plan == ["inspect", "answer"]
    assert ctx.progress == "advanced: made a bounded step"
    assert [event["stimulus"] for event in ctx.recent_events] == ["second", "third"]
    assert "intent:third" in ctx.summary


def test_learning_store_records_deduplicates_recalls_and_restores() -> None:
    store = PersistentLearningStore()
    reflection = {
        "thought": "Stress loops shrink the available plan space.",
        "insight": "When stress rises, break the plan into the next tiny action.",
        "_type": "reflection",
    }

    insight = store.record_reflection(tick=4, reflection=reflection)
    assert insight is not None
    confidence_before = insight.confidence
    duplicate = store.record_reflection(tick=5, reflection=reflection)

    assert duplicate is insight
    assert duplicate.confidence > confidence_before
    recalled = store.recall("stress plan tiny action", limit=1)
    assert [item.id for item in recalled] == [insight.id]

    restored = PersistentLearningStore()
    restored.restore(store.to_dict())
    restored_context = restored.context("stress plan tiny action", limit=1)

    assert restored_context["insight_count"] == 1
    assert restored_context["learned_insights"][0]["id"] == insight.id
    assert restored_context["learned_insights"][0]["learning"] == insight.learning


def test_null_learning_store_noops() -> None:
    store = NullLearningStore()

    ctx = store.record_interaction(1, "stimulus", {"response": "ok"})

    assert ctx.interaction_count == 0
    assert store.record_reflection(1, {"insight": "important"}) is None
    assert store.recall("important") == []
    assert store.context()["type"] == "null"
    assert store.to_dict()["insight_count"] == 0


def test_harness_records_learning_interactions() -> None:
    team = ScriptedTeam(
        stimulus_response=lambda stimulus: {
            "response": f"ok:{stimulus}",
            "planning": {
                "intent": "answer from learned context",
                "next_actions": ["verify continuity"],
                "goal_progress": "none",
            },
        },
    )

    result = run_loop(ticks=2, team=team, stimulus_plan={1: "remember this"})
    ctx = result.learning["session_context"]

    assert result.errors == []
    assert result.learning["type"] == "persistent"
    assert ctx["interaction_count"] == 1
    assert ctx["last_intent"] == "answer from learned context"
    assert ctx["current_plan"] == ["verify continuity"]


def test_learning_disabled_does_not_record_interactions() -> None:
    team = ScriptedTeam(stimulus_response=lambda stimulus: {"response": stimulus})

    result = run_loop(
        ticks=1,
        team=team,
        flags_overrides={"self_learning_enabled": False},
        stimulus_plan={1: "ignored while disabled"},
    )

    assert result.errors == []
    assert result.learning["session_context"]["interaction_count"] == 0
    assert result.learning["learned_insights"] == []


def test_loop_state_snapshot_exposes_compact_learning_context() -> None:
    team = ScriptedTeam(
        stimulus_response=lambda stimulus: {"response": f"ok:{stimulus}"}
    )
    harness = LoopHarness(team=team)
    loop = harness.build()

    async def drive() -> None:
        await loop.submit_stimulus("snapshot learning")
        await loop._tick()

    asyncio.run(drive())
    snapshots = loop.event_bus.history(EventTypes.STATE_SNAPSHOT)

    assert snapshots
    learning = snapshots[-1].payload["learning"]
    assert learning["type"] == "persistent"
    assert learning["session_context"]["interaction_count"] == 1
    assert learning["learned_insights"] == []


def test_checkpoint_restore_preserves_learning_store(tmp_path: Path) -> None:
    store = PersistentLearningStore()
    store.record_interaction(
        tick=2,
        stimulus="persist learning",
        result={"response": "ok", "planning": {"intent": "persist insight"}},
    )
    insight = store.record_reflection(
        tick=3,
        reflection={"insight": "Persisted insights should survive restart."},
    )
    assert insight is not None

    loop, checkpoint = _build_loop_with_learning_checkpoint(tmp_path, store)
    try:
        checkpoint.save(loop._build_snapshot())
    finally:
        checkpoint.close()

    restored_store = PersistentLearningStore()
    loop2, checkpoint2 = _build_loop_with_learning_checkpoint(tmp_path, restored_store)
    try:
        assert loop2.restore_from_checkpoint() is True
        restored_context = restored_store.context("persisted insights", limit=1)
        assert restored_context["session_context"]["interaction_count"] == 1
        assert restored_context["learned_insights"][0]["id"] == insight.id
    finally:
        checkpoint2.close()


def test_team_injects_learning_context_without_llm_construction() -> None:
    store = PersistentLearningStore()
    insight = store.record_reflection(
        tick=1,
        reflection={"insight": "Tiny next actions prevent stress lock."},
    )
    assert insight is not None

    team = object.__new__(ConsciousnessTeam)
    team.flags = FeatureFlags()
    team.learning_store = store
    team.learning_recall_limit = 1
    team.goal_stack = NullGoalStack()
    team.memory_store = NullMemoryStore()
    team.memories = []
    team.emotion_history = []
    team.runtime_state = RuntimeState()
    team.hysteresis = HomeostaticHysteresisEngine.from_settings(
        Settings().hysteresis,
    )
    team._perception_agent = MagicMock()
    team._emotion_agent = MagicMock()
    team._memory_agent = MagicMock()
    team._planning_agent = MagicMock()

    team._update_agent_states()

    learning_context = team._planning_agent.session_state["learning_context"]
    assert learning_context["insight_count"] == 1
    assert learning_context["learned_insights"][0]["id"] == insight.id


def _build_loop_with_learning_checkpoint(
    tmp_path: Path,
    learning_store: PersistentLearningStore,
) -> tuple[ConsciousnessLoop, SqliteCheckpoint]:
    settings = Settings()
    settings.persistence.checkpoint_path = str(tmp_path / "checkpoint.db")
    flags = FeatureFlags()
    flags.persistence_enabled = True
    flags.self_learning_enabled = True

    runtime_state = RuntimeState()
    hysteresis = HomeostaticHysteresisEngine.from_settings(settings.hysteresis)
    team = ScriptedTeam(runtime_state=runtime_state, hysteresis=hysteresis)
    checkpoint = SqliteCheckpoint(settings.persistence.checkpoint_path)

    loop = ConsciousnessLoop(
        settings=settings,
        flags=flags,
        runtime_state=runtime_state,
        hysteresis=hysteresis,
        event_bus=AsyncioEventBus(),
        team=team,
        governance=NullGovernanceKernel(),
        circuit_breaker=NullCircuitBreaker(),
        event_store=NullEventStore(),
        checkpoint=checkpoint,
        observability=NullObservabilityCollector(),
        sleep_manager=NullSleepManager(),
        memory_consolidator=NullMemoryConsolidator(),
        learning_store=learning_store,
    )
    return loop, checkpoint
