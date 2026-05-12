"""Tests for deterministic context providers."""

from pathlib import Path

from src.contracts.context import ContextDocument, IContextProvider, NullContextProvider
from src.engine.context_providers import LocalFileContextProvider, StaticContextProvider


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
