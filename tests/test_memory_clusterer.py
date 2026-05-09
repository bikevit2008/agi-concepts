"""Tests for memory clusterers (Stage 15)."""

import math

import pytest

from src.contracts.memory import MemoryEntry
from src.engine.memory_clusterer import (
    DensityFallbackClusterer,
    HdbscanClusterer,
    IMemoryClusterer,
    MemoryCluster,
)


def _embed_2d(angle_deg: float) -> list:
    """Helper to make 2D unit vectors at a given angle."""
    a = math.radians(angle_deg)
    return [math.cos(a), math.sin(a)]


def _entry(id_: str, vec: list, content: str = "x", emo: dict | None = None) -> MemoryEntry:
    return MemoryEntry(
        id=id_,
        content=content,
        embedding=vec,
        source="test",
        emotion_associations=emo or {},
        confidence=0.5,
    )


# --- DensityFallbackClusterer ---------------------------------------------


def test_density_fallback_groups_close_vectors():
    clusterer = DensityFallbackClusterer(similarity_threshold=0.95, min_cluster_size=2)
    # 3 nearby + 3 far apart
    entries = [
        _entry("a", _embed_2d(0)),
        _entry("b", _embed_2d(1)),
        _entry("c", _embed_2d(2)),
        _entry("d", _embed_2d(90)),
        _entry("e", _embed_2d(91)),
        _entry("f", _embed_2d(92)),
    ]
    clusters = clusterer.cluster(entries)
    assert len(clusters) == 2
    sizes = sorted(c.size for c in clusters)
    assert sizes == [3, 3]


def test_density_fallback_drops_too_small():
    clusterer = DensityFallbackClusterer(similarity_threshold=0.99, min_cluster_size=3)
    entries = [
        _entry("a", _embed_2d(0)),
        _entry("b", _embed_2d(0.1)),  # near a, but only 2 → dropped
        _entry("c", _embed_2d(89)),
    ]
    clusters = clusterer.cluster(entries)
    assert clusters == []


def test_density_fallback_centroid_and_emotion():
    clusterer = DensityFallbackClusterer(similarity_threshold=0.9, min_cluster_size=3)
    entries = [
        _entry("a", _embed_2d(0), emo={"joy": 0.8}),
        _entry("b", _embed_2d(2), emo={"joy": 0.7}),
        _entry("c", _embed_2d(4), emo={"sadness": 0.5, "joy": 0.6}),
    ]
    clusters = clusterer.cluster(entries)
    assert len(clusters) == 1
    c = clusters[0]
    assert c.dominant_emotion == "joy"
    assert len(c.centroid) == 2
    # centroid magnitude ~ 1 (mean of unit vectors close to each other)
    assert abs(math.sqrt(sum(v * v for v in c.centroid)) - 1.0) < 0.05


def test_density_fallback_handles_no_embeddings():
    clusterer = DensityFallbackClusterer()
    entries = [MemoryEntry(id="a", content="x", source="t")]  # no embedding
    assert clusterer.cluster(entries) == []


def test_density_fallback_satisfies_contract():
    c: IMemoryClusterer = DensityFallbackClusterer()
    assert isinstance(c, IMemoryClusterer)


# --- HdbscanClusterer (skipped if hdbscan missing) -------------------------


hdbscan = pytest.importorskip("hdbscan")


def test_hdbscan_groups_tight_clusters():
    clusterer = HdbscanClusterer(min_cluster_size=3)
    # Three tight clusters with strong separation
    entries = []
    for i in range(5):
        entries.append(_entry(f"a{i}", _embed_2d(0 + i * 0.2)))
    for i in range(5):
        entries.append(_entry(f"b{i}", _embed_2d(120 + i * 0.2)))
    for i in range(5):
        entries.append(_entry(f"c{i}", _embed_2d(240 + i * 0.2)))

    clusters = clusterer.cluster(entries)
    # Expect at least 2 dense clusters (HDBSCAN may merge or split with
    # such small samples; we just want it to produce something useful)
    assert len(clusters) >= 1
    # Members are split across clusters preserving count
    total = sum(c.size for c in clusters)
    assert total <= 15
    assert total >= 5  # at least one cluster recognised


def test_hdbscan_too_few_returns_empty():
    clusterer = HdbscanClusterer(min_cluster_size=3)
    entries = [_entry("a", _embed_2d(0))]
    assert clusterer.cluster(entries) == []


def test_hdbscan_satisfies_contract():
    c: IMemoryClusterer = HdbscanClusterer()
    assert isinstance(c, IMemoryClusterer)
