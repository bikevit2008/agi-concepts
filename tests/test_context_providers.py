"""Tests for deterministic context providers."""

from pathlib import Path
from unittest.mock import MagicMock

from src.config.flags import FeatureFlags
from src.config.settings import Settings
from src.contracts.context import ContextDocument, IContextProvider, NullContextProvider
from src.contracts.goals import NullGoalStack
from src.contracts.learning import NullLearningStore
from src.contracts.memory import NullMemoryStore
from src.contracts.session import NullSharedSessionState
from src.contracts.tasks import NullTaskLedger
from src.core.runtime_state import RuntimeState
from src.engine.homeostatic_hysteresis import HomeostaticHysteresisEngine
from src.engine.context_providers import LocalFileContextProvider, StaticContextProvider
from src.team.consciousness_team import ConsciousnessTeam


def test_static_context_provider_ranks_by_token_overlap():
    provider: IContextProvider = StaticContextProvider(
        provider_id="notes",
        documents=[
            ContextDocument(id="a", name="sleep", text="circadian REM memory"),
            ContextDocument(id="b", name="tools", text="capability gated registry"),
        ],
    )
    answer = provider.query("memory sleep", limit=1)
    assert answer.documents[0].id == "a"
    assert answer.documents[0].score > 0


def test_local_file_context_provider_reads_allowed_files(tmp_path: Path):
    (tmp_path / "notes.md").write_text("shared session blackboard", encoding="utf-8")
    (tmp_path / "ignored.bin").write_text("shared session", encoding="utf-8")
    provider = LocalFileContextProvider(root_path=str(tmp_path))
    answer = provider.query("blackboard", limit=5)
    assert len(answer.documents) == 1
    assert answer.documents[0].name == "notes.md"
    assert "shared session" in answer.text


def test_null_context_provider_satisfies_contract():
    provider: IContextProvider = NullContextProvider()
    assert provider.query("anything").documents == []


def test_team_injects_context_provider_results_with_provenance():
    provider = StaticContextProvider(
        provider_id="notes",
        documents=[
            ContextDocument(
                id="doc-1",
                name="stage39.md",
                uri="file:///stage39.md",
                text="context providers must preserve provenance",
            )
        ],
    )
    team = object.__new__(ConsciousnessTeam)
    team.flags = FeatureFlags()
    team.runtime_state = RuntimeState()
    team.hysteresis = HomeostaticHysteresisEngine.from_settings(Settings().hysteresis)
    team.goal_stack = NullGoalStack()
    team.task_ledger = NullTaskLedger()
    team.learning_store = NullLearningStore()
    team.shared_session = NullSharedSessionState()
    team.memory_store = NullMemoryStore()
    team.context_providers = [provider]
    team.context_provider_limit = 1
    team.context_max_document_chars = 120
    team.memories = []
    team.emotion_history = []
    team._perception_agent = MagicMock()
    team._emotion_agent = MagicMock()
    team._memory_agent = MagicMock()
    team._planning_agent = MagicMock()

    team._update_agent_states()

    external = team._planning_agent.session_state["external_context"]
    assert external["document_count"] == 1
    assert external["documents"][0]["provider_id"] == "notes"
    assert external["documents"][0]["text"] == (
        "context providers must preserve provenance"
    )
    assert external["provenance"] == [
        {
            "provider_id": "notes",
            "document_id": "doc-1",
            "name": "stage39.md",
            "uri": "file:///stage39.md",
            "score": 0.0,
        }
    ]
