"""Integration tests: memory store + provenance wired into ConsciousnessTeam.

Verify:
- New memories from Memory agent get persisted to the store, not just
  the legacy `team.memories` list.
- Retrieval populates pre_retrieved_memories before each Memory call.
- Provenance tracker filters out hallucinated `recalled_memories`.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.config.flags import FeatureFlags
from src.config.settings import ModelSettings
from src.contracts.governance import NullGovernanceKernel
from src.contracts.memory import MemoryEntry, ProvenanceVerdict
from src.core.event_bus import EventBus
from src.core.runtime_state import RuntimeState
from src.engine.homeostatic_hysteresis import HomeostaticHysteresisEngine
from src.persistence.embedder import HashingEmbedder
from src.persistence.memory_store import InMemoryMemoryStore
from src.persistence.provenance import EmbeddingProvenanceTracker


def _make_team(memory_store, provenance_tracker, flags=None):
    """Build a ConsciousnessTeam with mocked LLM agents."""
    from src.config.settings import HysteresisSettings
    from src.team.consciousness_team import ConsciousnessTeam

    flags = flags or FeatureFlags()
    runtime_state = RuntimeState()
    hysteresis = HomeostaticHysteresisEngine.from_settings(HysteresisSettings())

    with patch("src.team.consciousness_team.create_perception_agent") as p, \
         patch("src.team.consciousness_team.create_emotion_agent") as e, \
         patch("src.team.consciousness_team.create_memory_agent") as m, \
         patch("src.team.consciousness_team.create_planning_agent") as pl, \
         patch("src.team.consciousness_team.create_reflection_agent") as r:
        # Create stub agents — every .run() returns a structured response we control
        for create in (p, e, m, pl, r):
            create.return_value = MagicMock()
            create.return_value.session_state = {}
            create.return_value.model = MagicMock()
            create.return_value.model.temperature = 0.7
            create.return_value.model.max_tokens = 512

        team = ConsciousnessTeam(
            model_settings=ModelSettings(),
            runtime_state=runtime_state,
            hysteresis=hysteresis,
            flags=flags,
            event_bus=EventBus(),
            governance=NullGovernanceKernel(),
            memory_store=memory_store,
            provenance_tracker=provenance_tracker,
        )
    return team


def _stub_agent_response(content):
    resp = MagicMock()
    resp.content = content
    return resp


def test_memory_pre_retrieves_real_candidates():
    """Memory agent should see only stored memories in its session_state."""
    embedder = HashingEmbedder()
    store = InMemoryMemoryStore(
        embedder=embedder, real_threshold=0.6, uncertain_threshold=0.3
    )
    store.store(MemoryEntry(id="", content="we discussed neural networks", source="user"))
    store.store(MemoryEntry(id="", content="totally unrelated content", source="user"))

    tracker = EmbeddingProvenanceTracker(embedder=embedder)
    team = _make_team(store, tracker)

    # Stub Memory agent to capture session_state at call time
    captured_state = {}

    def memory_run(prompt):
        captured_state.update(team._memory_agent.session_state)
        return _stub_agent_response(
            '{"recalled_memories": [], "new_memory_to_store": null, "relevance_score": 0.5, "emotional_associations": {}}'
        )

    team._memory_agent.run = MagicMock(side_effect=memory_run)
    team._perception_agent.run = MagicMock(return_value=_stub_agent_response(None))
    team._emotion_agent.run = MagicMock(return_value=_stub_agent_response(None))
    team._planning_agent.run = MagicMock(
        return_value=_stub_agent_response(
            '{"response": "ok", "intent": "answer", "confidence": 0.9, "next_actions": [], "internal_state_summary": ""}'
        )
    )

    team.process_stimulus_sync("we discussed neural networks")

    pre_retrieved = captured_state.get("pre_retrieved_memories", [])
    assert len(pre_retrieved) >= 1
    assert any("neural networks" in p["content"] for p in pre_retrieved)
    stored_memories = captured_state.get("stored_memories", [])
    assert any("neural networks" in memory for memory in stored_memories)
    assert team.memories == []


def test_memory_provenance_filters_hallucinated_recalls():
    """Provenance tracker must drop recalls that don't match the store."""
    embedder = HashingEmbedder()
    store = InMemoryMemoryStore(embedder=embedder, real_threshold=0.85)
    store.store(MemoryEntry(id="", content="user prefers tea", source="user"))

    tracker = EmbeddingProvenanceTracker(
        embedder=embedder, real_threshold=0.85, uncertain_threshold=0.4
    )
    team = _make_team(store, tracker)

    # Memory agent fabricates a recall that doesn't exist in the store
    team._memory_agent.run = MagicMock(
        return_value=_stub_agent_response(
            '{"recalled_memories": ["the user is currently piloting a spaceship"], '
            '"new_memory_to_store": null, "relevance_score": 0.5, "emotional_associations": {}}'
        )
    )
    team._perception_agent.run = MagicMock(return_value=_stub_agent_response(None))
    team._emotion_agent.run = MagicMock(return_value=_stub_agent_response(None))
    team._planning_agent.run = MagicMock(
        return_value=_stub_agent_response(
            '{"response": "ok", "intent": "answer", "confidence": 0.9, "next_actions": [], "internal_state_summary": ""}'
        )
    )

    result = team.process_stimulus_sync("user query")

    # Hallucinated recall should be filtered out
    memory = result.get("memory") or {}
    assert memory.get("recalled_memories", []) == []
    # Provenance verdict should be reported
    provenance = result.get("memory_provenance") or {}
    assert any(v == ProvenanceVerdict.HALLUCINATED.value for v in provenance.values())


def test_memory_new_memory_persisted_to_store():
    """When agent suggests a new memory, it must hit the vector store."""
    embedder = HashingEmbedder()
    store = InMemoryMemoryStore(embedder=embedder)
    tracker = EmbeddingProvenanceTracker(embedder=embedder)
    team = _make_team(store, tracker)

    assert store.count() == 0

    team._memory_agent.run = MagicMock(
        return_value=_stub_agent_response(
            '{"recalled_memories": [], "new_memory_to_store": "NEW MEMORY: user owns a cat", '
            '"relevance_score": 0.8, "emotional_associations": {"joy": 0.5}}'
        )
    )
    team._perception_agent.run = MagicMock(return_value=_stub_agent_response(None))
    team._emotion_agent.run = MagicMock(return_value=_stub_agent_response(None))
    team._planning_agent.run = MagicMock(
        return_value=_stub_agent_response(
            '{"response": "ok", "intent": "answer", "confidence": 0.9, "next_actions": [], "internal_state_summary": ""}'
        )
    )

    team.process_stimulus_sync("does the user have pets?")

    assert store.count() == 1
    assert "user owns a cat" in store.all_contents()[0]
    # And in the legacy list
    assert any("cat" in m for m in team.memories)


def test_memory_disabled_skips_store_calls():
    """memory_store_enabled=false: pipeline still works, no calls to store."""
    embedder = HashingEmbedder()
    store = InMemoryMemoryStore(embedder=embedder)
    tracker = EmbeddingProvenanceTracker(embedder=embedder)

    flags = FeatureFlags()
    flags.memory_store_enabled = False
    flags.provenance_tracking_enabled = False
    team = _make_team(store, tracker, flags=flags)

    team._memory_agent.run = MagicMock(
        return_value=_stub_agent_response(
            '{"recalled_memories": [], "new_memory_to_store": "should not persist", '
            '"relevance_score": 0.5, "emotional_associations": {}}'
        )
    )
    team._perception_agent.run = MagicMock(return_value=_stub_agent_response(None))
    team._emotion_agent.run = MagicMock(return_value=_stub_agent_response(None))
    team._planning_agent.run = MagicMock(
        return_value=_stub_agent_response(
            '{"response": "ok", "intent": "answer", "confidence": 0.9, "next_actions": [], "internal_state_summary": ""}'
        )
    )

    team.process_stimulus_sync("test")

    # Vector store untouched (disabled), but legacy list updated
    assert store.count() == 0
    assert any("should not persist" in m for m in team.memories)


def test_team_snapshot_memories_prefers_store():
    embedder = HashingEmbedder()
    store = InMemoryMemoryStore(embedder=embedder)
    store.store(MemoryEntry(id="", content="stored semantic memory", source="test"))
    tracker = EmbeddingProvenanceTracker(embedder=embedder)
    team = _make_team(store, tracker)
    team.memories.append("legacy shadow memory")

    assert team.snapshot_memories() == ["stored semantic memory"]


def test_team_restore_memories_seeds_empty_store():
    embedder = HashingEmbedder()
    store = InMemoryMemoryStore(embedder=embedder)
    tracker = EmbeddingProvenanceTracker(embedder=embedder)
    team = _make_team(store, tracker)

    team.restore_memories(["restored memory"])

    assert team.memories == ["restored memory"]
    assert store.count() == 1
    assert store.all_contents() == ["restored memory"]
