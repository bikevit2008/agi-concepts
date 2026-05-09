"""Tests for LanceDbMemoryStore.

Skipped automatically if `lancedb` is not installed.
"""

from pathlib import Path

import pytest

from src.contracts.memory import MemoryEntry, ProvenanceVerdict
from src.persistence.embedder import HashingEmbedder

lancedb = pytest.importorskip("lancedb")
pyarrow = pytest.importorskip("pyarrow")

from src.persistence.memory_store import LanceDbMemoryStore  # noqa: E402


def _make_store(tmp_path: Path, **kwargs) -> LanceDbMemoryStore:
    return LanceDbMemoryStore(
        uri=str(tmp_path / "lance"),
        table_name="test_memories",
        embedder=HashingEmbedder(dimension=64),  # smaller dim → faster tests
        **kwargs,
    )


def test_lancedb_store_and_count(tmp_path: Path):
    store = _make_store(tmp_path)
    assert store.count() == 0
    store.store(MemoryEntry(id="", content="user likes Python", source="chat"))
    assert store.count() == 1
    store.close()


def test_lancedb_retrieve_returns_match(tmp_path: Path):
    store = _make_store(tmp_path, real_threshold=0.6, uncertain_threshold=0.3)
    store.store(MemoryEntry(id="", content="user prefers tea over coffee", source="chat"))

    results = store.retrieve("user prefers tea over coffee")
    assert len(results) >= 1
    top = results[0]
    assert top.verdict == ProvenanceVerdict.REAL
    assert top.entry.content == "user prefers tea over coffee"
    store.close()


def test_lancedb_retrieve_persistence_across_open(tmp_path: Path):
    """Memories survive store close/reopen — file-backed storage."""
    store1 = _make_store(tmp_path)
    store1.store(MemoryEntry(id="m_persistent", content="persistent memory", source="t"))
    store1.close()

    # Reopen with same uri/table
    store2 = _make_store(tmp_path)
    assert store2.count() == 1
    contents = store2.all_contents()
    assert "persistent memory" in contents
    store2.close()


def test_lancedb_all_entries_preserves_metadata(tmp_path: Path):
    store = _make_store(tmp_path)
    store.store(
        MemoryEntry(
            id="",
            content="meeting notes",
            source="user",
            emotion_associations={"joy": 0.7, "anticipation": 0.3},
            confidence=0.85,
        )
    )
    entries = store.all_entries()
    assert len(entries) == 1
    e = entries[0]
    assert e.content == "meeting notes"
    assert e.source == "user"
    assert e.emotion_associations == {"joy": 0.7, "anticipation": 0.3}
    assert abs(e.confidence - 0.85) < 1e-3
    store.close()


def test_lancedb_emotion_filter(tmp_path: Path):
    store = _make_store(tmp_path)
    store.store(
        MemoryEntry(
            id="",
            content="happy memory",
            source="t",
            emotion_associations={"joy": 0.9},
        )
    )
    store.store(
        MemoryEntry(
            id="",
            content="similar happy memory text",
            source="t",
            emotion_associations={"sadness": 0.8},
        )
    )

    results = store.retrieve("happy memory", emotion_filter={"joy": 0.5})
    # Only the "joy" memory should pass the filter
    joy_count = sum(
        1 for r in results if r.entry.emotion_associations.get("joy", 0.0) >= 0.5
    )
    assert joy_count >= 1
    sad_count = sum(
        1 for r in results if r.entry.emotion_associations.get("sadness", 0.0) >= 0.5
    )
    assert sad_count == 0
    store.close()
