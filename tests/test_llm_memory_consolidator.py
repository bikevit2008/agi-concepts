"""Tests for LlmMemoryConsolidator (Stage 15)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock


from src.contracts.governance import (
    AuditResult,
    GovernanceDecision,
    NullConstitutionalAuditor,
    PolicySeverity,
    RiskTier,
    ConstitutionalViolation,
)
from src.contracts.memory import MemoryEntry
from src.engine.llm_memory_consolidator import (
    LlmMemoryConsolidator,
    _build_reflection_prompt,
)
from src.engine.memory_clusterer import DensityFallbackClusterer, MemoryCluster
from src.persistence.embedder import HashingEmbedder
from src.persistence.memory_store import InMemoryMemoryStore


def _entry(id_: str, content: str, emo: dict | None = None) -> MemoryEntry:
    return MemoryEntry(
        id=id_,
        content=content,
        embedding=HashingEmbedder().embed(content),
        source="test",
        emotion_associations=emo or {},
        confidence=0.5,
    )


def _make_store_with(entries: list[MemoryEntry]) -> InMemoryMemoryStore:
    s = InMemoryMemoryStore(embedder=HashingEmbedder())
    for e in entries:
        s.store(e)
    return s


# --- Prompt construction ---------------------------------------------------


def test_build_reflection_prompt_includes_all_members():
    cluster = MemoryCluster(
        id=0,
        member_ids=["a", "b"],
        members=[
            _entry("a", "user likes Python", emo={"joy": 0.8}),
            _entry("b", "user likes AI", emo={"joy": 0.6}),
        ],
        centroid=[0.0] * 16,
        dominant_emotion="joy",
        avg_confidence=0.5,
    )
    prompt = _build_reflection_prompt(cluster, "joy")
    assert "joy" in prompt
    assert "user likes Python" in prompt
    assert "user likes AI" in prompt
    # Anti-fabrication phrasing
    assert "Do not invent" in prompt or "do not" in prompt.lower()


# --- NREM phase ------------------------------------------------------------


def test_nrem_strengthens_paired_memories_and_bumps_importance():
    entries = [
        _entry("a", "A", emo={"joy": 0.5}),
        _entry("b", "B", emo={"joy": 0.4}),
        _entry("c", "C", emo={"sadness": 0.3}),  # no shared emo with a/b
    ]
    store = _make_store_with(entries)
    cons = LlmMemoryConsolidator(memory_store=store)

    stats = cons.consolidate_nrem([])

    assert stats["consolidated"] == 1  # one shared-emotion pair
    assert stats["importance_bumped"] >= 1


def test_nrem_handles_empty_store():
    store = InMemoryMemoryStore(embedder=HashingEmbedder())
    cons = LlmMemoryConsolidator(memory_store=store)
    stats = cons.consolidate_nrem([])
    assert stats["phase"] == "nrem"
    assert stats["consolidated"] == 0


# --- REM phase: stub LLM invoker ------------------------------------------


def _make_invoker(text: str, theme: str = "joy", confidence: float = 0.85):
    """Returns a callable matching ReflectionInvoker that yields a known
    abstraction object (using SimpleNamespace as a stand-in for the
    Pydantic ReflectionAbstraction)."""

    def invoke(prompt, members):
        return SimpleNamespace(
            abstraction=text,
            theme=theme,
            confidence=confidence,
            supporting_memory_ids=[m.id for m in members],
            reasoning="stub reasoning",
        )

    return invoke


def test_rem_creates_abstractions_for_clusters():
    """Use texts with high HashingEmbedder cosine similarity so clusters form."""
    entries = [
        _entry("a", "user enjoys learning programming AI", emo={"joy": 0.9}),
        _entry("b", "user enjoys learning programming AI methods", emo={"joy": 0.85}),
        _entry("c", "user enjoys learning programming AI concepts", emo={"joy": 0.8}),
        _entry("d", "totally different cats and dogs sitting", emo={"calm": 0.5}),
    ]
    store = _make_store_with(entries)
    pre_count = store.count()

    cons = LlmMemoryConsolidator(
        memory_store=store,
        embedder=HashingEmbedder(),
        clusterer=DensityFallbackClusterer(similarity_threshold=0.5, min_cluster_size=3),
        reflection_invoker=_make_invoker(
            "user enjoys learning programming and AI", confidence=0.9
        ),
        min_provenance_similarity=0.0,  # disable provenance for this test
    )
    stats = cons.consolidate_rem([])

    assert stats["clusters_evaluated"] >= 1
    assert stats["consolidated"] >= 1
    # New abstraction memory persisted
    assert store.count() > pre_count
    # And tagged correctly
    found = [e for e in store.all_entries() if e.source == "rem_consolidation"]
    assert any("enjoys learning" in e.content for e in found)


def _shared_text_entries(prefix: str = "alpha") -> list[MemoryEntry]:
    """Generate 3 entries with high pairwise hashing-embedder similarity."""
    return [
        _entry("a", f"{prefix} {prefix} repeated text aaa", emo={"joy": 0.9}),
        _entry("b", f"{prefix} {prefix} repeated text bbb", emo={"joy": 0.85}),
        _entry("c", f"{prefix} {prefix} repeated text ccc", emo={"joy": 0.8}),
    ]


def test_rem_falls_back_when_no_invoker():
    entries = _shared_text_entries()
    store = _make_store_with(entries)
    cons = LlmMemoryConsolidator(
        memory_store=store,
        clusterer=DensityFallbackClusterer(similarity_threshold=0.5, min_cluster_size=3),
        reflection_invoker=None,  # forces string-concat fallback
        min_provenance_similarity=0.0,
    )
    stats = cons.consolidate_rem([])
    assert stats["consolidated"] >= 1
    new = [e for e in store.all_entries() if e.source == "rem_consolidation"]
    assert any("[abstraction:" in e.content for e in new)


def test_rem_blocks_hallucinated_abstraction_via_provenance():
    entries = _shared_text_entries()
    store = _make_store_with(entries)
    cons = LlmMemoryConsolidator(
        memory_store=store,
        embedder=HashingEmbedder(),
        clusterer=DensityFallbackClusterer(similarity_threshold=0.5, min_cluster_size=3),
        reflection_invoker=_make_invoker(
            "completely unrelated text about quantum physics moon landing 1969",
            confidence=0.95,
        ),
        min_provenance_similarity=0.7,  # strict
    )
    stats = cons.consolidate_rem([])
    assert stats["blocked_provenance"] >= 1
    new = [e for e in store.all_entries() if e.source == "rem_consolidation"]
    # The hallucinated abstraction must NOT have been persisted
    assert new == []


def test_rem_blocks_constitutional_denial():
    """Configure an auditor that always returns DENY_CONSTITUTION."""
    deny_auditor = MagicMock(spec=NullConstitutionalAuditor)
    deny_auditor.audit_tool_call.return_value = AuditResult(
        approved=False,
        decision=GovernanceDecision.DENY_CONSTITUTION,
        risk_tier=RiskTier.HIGH,
        risk_score=95.0,
        violations=[
            ConstitutionalViolation(
                policy_id="TEST_BLOCK",
                severity=PolicySeverity.CRITICAL,
                message="forbidden",
            )
        ],
        rationale="test policy",
    )

    entries = _shared_text_entries()
    store = _make_store_with(entries)
    cons = LlmMemoryConsolidator(
        memory_store=store,
        clusterer=DensityFallbackClusterer(similarity_threshold=0.5, min_cluster_size=3),
        reflection_invoker=_make_invoker("a meaningful summary", confidence=0.9),
        auditor=deny_auditor,
        min_provenance_similarity=0.0,
    )
    stats = cons.consolidate_rem([])
    assert stats["blocked_constitution"] >= 1


def test_rem_idempotency_dedups_same_theme():
    entries = _shared_text_entries()
    store = _make_store_with(entries)
    cons = LlmMemoryConsolidator(
        memory_store=store,
        clusterer=DensityFallbackClusterer(similarity_threshold=0.5, min_cluster_size=3),
        reflection_invoker=_make_invoker("first abstraction"),
        min_provenance_similarity=-1.0,  # disable provenance for this test
        dedup_theme_ttl_seconds=300.0,
    )
    s1 = cons.consolidate_rem([])
    s2 = cons.consolidate_rem([])
    # First cycle stores; second sees the same theme cached
    assert s1["consolidated"] >= 1
    assert s2.get("deduped", 0) >= 1


def test_rem_skips_when_too_few_primary_entries():
    entries = [_entry("a", "x", emo={"joy": 1.0})]
    store = _make_store_with(entries)
    cons = LlmMemoryConsolidator(memory_store=store)
    stats = cons.consolidate_rem([])
    assert stats["consolidated"] == 0
    assert stats.get("skipped_reason") in (
        "too_few_entries",
        "too_few_primary",
        "no_clusters",
    )


def test_rem_does_not_abstract_over_abstractions():
    """Memories with source='rem_consolidation' are excluded from clustering."""
    abstraction = _entry("abs1", "older abstraction", emo={"joy": 0.7})
    abstraction.source = "rem_consolidation"
    entries = [
        abstraction,
        _entry("a", "fresh memory one"),
        _entry("b", "fresh memory two"),
    ]
    store = _make_store_with(entries)
    cons = LlmMemoryConsolidator(memory_store=store, min_cluster_size=3)
    stats = cons.consolidate_rem([])
    # Only 2 primary entries exist after filtering — below min_cluster_size
    assert stats.get("consolidated", 0) == 0


def test_rem_caps_clusters_per_cycle():
    """Configure max_clusters_per_cycle=1; even 3 clusters → 1 LLM call."""
    # Make 3 well-separated clusters
    import math as _math

    def vec(angle):
        a = _math.radians(angle)
        return [_math.cos(a), _math.sin(a)]

    entries = []
    for ang, name in ((0, "p"), (120, "q"), (240, "r")):
        for i in range(3):
            entries.append(
                MemoryEntry(
                    id=f"{name}{i}",
                    content=f"{name} content {i}",
                    embedding=vec(ang + i * 0.1),
                    source="test",
                    emotion_associations={f"emo_{name}": 0.8},
                    confidence=0.5,
                )
            )

    store = _make_store_with(entries)
    invoker_calls = []

    def invoker(prompt, members):
        invoker_calls.append(len(members))
        return SimpleNamespace(
            abstraction="summary " + members[0].id,
            theme="t" + str(len(invoker_calls)),
            confidence=0.9,
            supporting_memory_ids=[m.id for m in members],
            reasoning="",
        )

    cons = LlmMemoryConsolidator(
        memory_store=store,
        embedder=HashingEmbedder(),
        clusterer=DensityFallbackClusterer(similarity_threshold=0.95, min_cluster_size=3),
        reflection_invoker=invoker,
        min_provenance_similarity=0.0,
        max_clusters_per_cycle=1,
    )
    stats = cons.consolidate_rem([])
    assert len(invoker_calls) <= 1
    assert stats["clusters_evaluated"] <= 1


def test_satisfies_contract():
    from src.contracts.sleep import IMemoryConsolidator

    store = InMemoryMemoryStore(embedder=HashingEmbedder())
    cons: IMemoryConsolidator = LlmMemoryConsolidator(memory_store=store)
    assert isinstance(cons, IMemoryConsolidator)


def test_to_dict_shape():
    store = InMemoryMemoryStore(embedder=HashingEmbedder())
    cons = LlmMemoryConsolidator(memory_store=store)
    d = cons.to_dict()
    assert d["type"] == "llm_consolidator"
    assert "clusterer" in d
    assert d["uses_llm"] is False
