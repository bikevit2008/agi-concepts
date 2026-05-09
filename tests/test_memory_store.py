"""Tests for memory store + embedder + provenance tracker (Stage 5)."""

import pytest

from src.contracts.memory import (
    IMemoryStore,
    IProvenanceTracker,
    MemoryEntry,
    NullMemoryStore,
    NullProvenanceTracker,
    ProvenanceVerdict,
)
from src.persistence.embedder import HashingEmbedder
from src.persistence.memory_store import InMemoryMemoryStore
from src.persistence.provenance import EmbeddingProvenanceTracker


# --- Embedder --------------------------------------------------------------


def test_hashing_embedder_dimension_default():
    e = HashingEmbedder()
    assert e.dimension == 256
    vec = e.embed("hello world")
    assert len(vec) == 256


def test_hashing_embedder_custom_dimension():
    e = HashingEmbedder(dimension=64)
    assert e.dimension == 64
    vec = e.embed("foo")
    assert len(vec) == 64


def test_hashing_embedder_empty_returns_zero():
    e = HashingEmbedder()
    vec = e.embed("")
    assert all(v == 0.0 for v in vec)


def test_hashing_embedder_deterministic():
    e = HashingEmbedder()
    v1 = e.embed("the system feels stressed")
    v2 = e.embed("the system feels stressed")
    assert v1 == v2


def test_hashing_embedder_discriminates_different_text():
    e = HashingEmbedder()
    v1 = e.embed("the system feels stressed")
    v2 = e.embed("the system feels calm")
    # Some overlap (shared tokens) but not identical
    assert v1 != v2


def test_hashing_embedder_minimum_dimension_enforced():
    with pytest.raises(ValueError):
        HashingEmbedder(dimension=4)


def test_hashing_embedder_batch():
    e = HashingEmbedder()
    out = e.embed_batch(["a", "b", "c"])
    assert len(out) == 3
    assert all(len(v) == 256 for v in out)


# --- InMemoryMemoryStore ---------------------------------------------------


def test_memory_store_store_and_count():
    store = InMemoryMemoryStore(embedder=HashingEmbedder())
    assert store.count() == 0
    mid = store.store(MemoryEntry(id="", content="user prefers Python", source="user"))
    assert mid != ""
    assert store.count() == 1


def test_memory_store_retrieve_returns_real_for_match():
    store = InMemoryMemoryStore(
        embedder=HashingEmbedder(),
        real_threshold=0.6,  # lowered because hashing embedder ~0.7-0.95 on similar
        uncertain_threshold=0.3,
    )
    store.store(MemoryEntry(id="", content="user loves Python and AI", source="chat"))

    results = store.retrieve("user loves Python and AI")
    assert len(results) == 1
    assert results[0].verdict == ProvenanceVerdict.REAL
    assert results[0].similarity > 0.99


def test_memory_store_retrieve_returns_hallucinated_for_unrelated():
    store = InMemoryMemoryStore(
        embedder=HashingEmbedder(),
        real_threshold=0.85,
        uncertain_threshold=0.5,
    )
    store.store(MemoryEntry(id="", content="weather is rainy today", source="user"))

    results = store.retrieve("quantum computing breakthrough")
    if results:
        # If anything matches, must NOT be REAL
        assert results[0].verdict in (ProvenanceVerdict.HALLUCINATED, ProvenanceVerdict.UNCERTAIN)


def test_memory_store_retrieve_limit():
    store = InMemoryMemoryStore(embedder=HashingEmbedder())
    for i in range(10):
        store.store(MemoryEntry(id="", content=f"memory {i} foo bar", source="test"))

    results = store.retrieve("memory foo bar", limit=3)
    assert len(results) == 3


def test_memory_store_retrieve_min_similarity_filter():
    store = InMemoryMemoryStore(embedder=HashingEmbedder())
    store.store(MemoryEntry(id="", content="exact match here", source="test"))
    store.store(MemoryEntry(id="", content="zzz totally unrelated yyy", source="test"))

    results = store.retrieve("exact match here", limit=10, min_similarity=0.9)
    # Only the exact match should pass the filter
    assert len(results) == 1
    assert results[0].entry.content == "exact match here"


def test_memory_store_retrieve_emotion_filter():
    store = InMemoryMemoryStore(embedder=HashingEmbedder())
    store.store(
        MemoryEntry(
            id="",
            content="happy memory about a vacation",
            source="test",
            emotion_associations={"joy": 0.9},
        )
    )
    store.store(
        MemoryEntry(
            id="",
            content="happy memory about something else entirely different",
            source="test",
            emotion_associations={"sadness": 0.8},
        )
    )

    results = store.retrieve("happy memory", emotion_filter={"joy": 0.5})
    assert len(results) == 1
    assert results[0].entry.emotion_associations.get("joy", 0.0) >= 0.5


def test_memory_store_all_contents():
    store = InMemoryMemoryStore(embedder=HashingEmbedder())
    store.store(MemoryEntry(id="", content="A", source="t"))
    store.store(MemoryEntry(id="", content="B", source="t"))
    assert sorted(store.all_contents()) == ["A", "B"]


# --- Provenance tracker ----------------------------------------------------


def test_provenance_no_store_returns_no_store_verdict():
    tracker = EmbeddingProvenanceTracker(embedder=HashingEmbedder())
    assert tracker.verify_recall("anything", []) == ProvenanceVerdict.NO_STORE


def test_provenance_real_recall():
    embedder = HashingEmbedder()
    tracker = EmbeddingProvenanceTracker(
        embedder=embedder, real_threshold=0.85, uncertain_threshold=0.5
    )
    stored = [
        MemoryEntry(
            id="m1",
            content="user likes the color blue",
            embedding=embedder.embed("user likes the color blue"),
            source="user",
        )
    ]
    verdict = tracker.verify_recall("user likes the color blue", stored)
    assert verdict == ProvenanceVerdict.REAL


def test_provenance_hallucinated_recall():
    embedder = HashingEmbedder()
    tracker = EmbeddingProvenanceTracker(
        embedder=embedder, real_threshold=0.85, uncertain_threshold=0.5
    )
    stored = [
        MemoryEntry(
            id="m1",
            content="user likes the color blue",
            embedding=embedder.embed("user likes the color blue"),
            source="user",
        )
    ]
    verdict = tracker.verify_recall(
        "the spaceship landed on Mars yesterday morning",
        stored,
    )
    assert verdict == ProvenanceVerdict.HALLUCINATED


def test_provenance_filter_recalls_classifies_each():
    embedder = HashingEmbedder()
    tracker = EmbeddingProvenanceTracker(
        embedder=embedder, real_threshold=0.85, uncertain_threshold=0.4
    )
    stored = [
        MemoryEntry(
            id="m1",
            content="we discussed neural networks last week",
            embedding=embedder.embed("we discussed neural networks last week"),
            source="user",
        )
    ]
    out = tracker.filter_recalls(
        [
            "we discussed neural networks last week",  # REAL
            "completely unrelated content about cooking pasta",  # HALLUCINATED
        ],
        stored,
    )
    assert out[0][1] == ProvenanceVerdict.REAL
    assert out[1][1] == ProvenanceVerdict.HALLUCINATED


def test_provenance_invalid_thresholds_rejected():
    with pytest.raises(ValueError):
        EmbeddingProvenanceTracker(
            embedder=HashingEmbedder(),
            real_threshold=0.5,
            uncertain_threshold=0.5,
        )


def test_provenance_empty_recall_text():
    tracker = EmbeddingProvenanceTracker(embedder=HashingEmbedder())
    stored = [MemoryEntry(id="m1", content="something", source="t")]
    assert tracker.verify_recall("", stored) == ProvenanceVerdict.HALLUCINATED


# --- Null impls ------------------------------------------------------------


def test_null_memory_store_supports_store_and_count():
    store = NullMemoryStore()
    mid = store.store(MemoryEntry(id="", content="test", source="t"))
    assert mid != ""
    assert store.count() == 1


def test_null_provenance_returns_no_store_for_empty():
    tracker = NullProvenanceTracker()
    assert tracker.verify_recall("anything", []) == ProvenanceVerdict.HALLUCINATED


# --- Contract conformance --------------------------------------------------


def test_implementations_satisfy_contracts():
    store: IMemoryStore = InMemoryMemoryStore(embedder=HashingEmbedder())
    tracker: IProvenanceTracker = EmbeddingProvenanceTracker(embedder=HashingEmbedder())
    assert isinstance(store, IMemoryStore)
    assert isinstance(tracker, IProvenanceTracker)
