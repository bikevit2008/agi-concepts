"""Tests for shared session state and task-ledger stages."""

import asyncio

from src.bus.event_types import EventTypes
from src.contracts.session import ISharedSessionState, NullSharedSessionState
from src.contracts.tasks import ITaskLedger, NullTaskLedger, TaskStatus
from src.engine.shared_session import PersistentSharedSessionState
from src.engine.task_ledger import PersistentTaskLedger
from src.experiments.harness import LoopHarness, ScriptedTeam, run_loop


def test_shared_session_round_trips_and_projects_context():
    state: ISharedSessionState = PersistentSharedSessionState(
        session_id="s1",
        max_recent_mutations=3,
    )
    state.update_namespace("runtime", {"energy_level": 0.7}, tick=1, source="test")
    state.update_namespace("goals", {"top": {"id": "g1"}}, tick=2, source="test")

    context = state.context(agent="Planning")
    assert context["session_id"] == "s1"
    assert context["namespaces"]["runtime"]["energy_level"] == 0.7
    assert context["namespaces"]["goals"]["top"]["id"] == "g1"

    restored = PersistentSharedSessionState(session_id="other")
    restored.restore(state.to_dict())
    assert restored.context()["session_id"] == "s1"
    assert restored.context()["namespaces"]["runtime"]["energy_level"] == 0.7


def test_null_shared_session_satisfies_contract():
    state: ISharedSessionState = NullSharedSessionState()
    assert state.update_namespace("runtime", {"x": 1}) == {}
    assert state.context()["type"] == "disabled"


def test_task_ledger_dedupes_dependencies_and_restores():
    ledger: ITaskLedger = PersistentTaskLedger(max_tasks=10)
    first = ledger.create("Draft next experiment", tick=1, goal_id="g1")
    assert first is not None
    duplicate = ledger.create("Draft next experiment", tick=2, goal_id="g1")
    assert duplicate is first

    blocked = ledger.create(
        "Run experiment",
        tick=3,
        goal_id="g1",
        dependencies=[first.id],
    )
    assert blocked is not None
    assert blocked.status == TaskStatus.BLOCKED

    ledger.update_status(first.id, TaskStatus.COMPLETED, tick=4)
    assert blocked in ledger.available_tasks(goal_id="g1")

    restored = PersistentTaskLedger()
    restored.restore(ledger.to_dict())
    assert restored.context(goal_id="g1")["task_count"] == 2


def test_null_task_ledger_satisfies_contract():
    ledger: ITaskLedger = NullTaskLedger()
    assert ledger.create("x", tick=1) is None
    assert ledger.available_tasks() == []
    assert ledger.context()["type"] == "disabled"


def test_harness_exposes_shared_session_snapshot():
    result = run_loop(ticks=3, stimulus_plan={1: "hello"})
    assert result.errors == []
    assert result.shared_session["type"] == "persistent"
    assert "runtime" in result.shared_session["namespaces"]
    assert "tasks" in result.shared_session["namespaces"]


def test_goal_pursuit_uses_available_task_and_records_completion():
    team = ScriptedTeam(
        stimulus_response=lambda s: {
            "response": f"done:{s}",
            "planning": {
                "goal_progress": "advanced",
                "goal_progress_reason": "task advanced",
            },
        },
    )
    harness = LoopHarness(
        team=team,
        settings_overrides={
            "goal_stack.pursuit_min_idle_ticks": 1,
            "goal_stack.pursuit_min_ticks_between_attempts": 1,
            "goal_stack.pursuit_progress_stale_after_ticks": 0,
        },
    )
    loop = harness.build()
    goal = loop.goal_stack.propose("Test durable task", priority=0.8, tick=0)
    assert goal is not None
    task = loop.task_ledger.create("Take first step", tick=0, goal_id=goal.id)
    assert task is not None

    asyncio.run(loop._tick())
    assert loop.task_ledger.tasks(status=TaskStatus.IN_PROGRESS)[0].id == task.id

    asyncio.run(loop._tick())
    completed = loop.task_ledger.tasks(status=TaskStatus.COMPLETED)
    assert completed and completed[0].id == task.id
    assert "[task:" in team.processed_results[0]["response"]


def test_lifecycle_events_are_emitted_for_stimulus_pipeline():
    team = ScriptedTeam(
        stimulus_response=lambda s: {
            "response": "ok",
            "planning": {"response": "ok"},
        },
    )
    loop = LoopHarness(team=team).build()

    async def run_once():
        await loop.submit_stimulus("hello")
        await loop._tick()

    asyncio.run(run_once())

    event_types = [event.event_type for event in loop.event_bus.history(limit=20)]
    assert EventTypes.PIPELINE_STARTED in event_types
    assert EventTypes.PIPELINE_COMPLETED in event_types
    assert EventTypes.AGENT_STEP_COMPLETED in event_types
