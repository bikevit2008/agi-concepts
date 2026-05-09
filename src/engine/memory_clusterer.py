"""Embedding-based clustering for REM-phase memory consolidation.

Two backends:

1. **HdbscanClusterer** — HDBSCAN density-based hierarchical clustering.
   Per dify-search SOTA 2026 it's the strongest option for sub-1000
   semantic clusters: handles variable density, labels noise, no `k`
   needed. Uses cosine distance via 1 - cos(x, y) precomputed.

2. **DensityFallbackClusterer** — pure-Python connected-components
   over a cosine-similarity threshold graph. Used when hdbscan isn't
   installed or for tiny datasets where HDBSCAN's overhead doesn't pay.

Both produce a list of `MemoryCluster` objects with member ids,
centroid embedding (mean-pooled), and dominant emotion (mode of
emotion_associations across members).
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

import structlog

from src.contracts.memory import MemoryEntry

logger = structlog.get_logger("consciousness.engine.memory_clusterer")


@dataclass
class MemoryCluster:
    """A semantically-coherent group of memories."""

    id: int  # cluster index; -1 means "noise / unclustered"
    member_ids: List[str]
    members: List[MemoryEntry]
    centroid: List[float] = field(default_factory=list)
    dominant_emotion: Optional[str] = None
    avg_confidence: float = 0.0

    @property
    def size(self) -> int:
        return len(self.members)


@runtime_checkable
class IMemoryClusterer(Protocol):
    def cluster(
        self, entries: List[MemoryEntry], min_cluster_size: int = 3
    ) -> List[MemoryCluster]:
        """Return clusters; entries with no cluster are NOT included
        (caller can detect them via id=-1 if implementation chooses)."""
        ...

    def to_dict(self) -> Dict[str, Any]:
        ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mean_embedding(members: List[MemoryEntry]) -> List[float]:
    if not members:
        return []
    dim = next((len(m.embedding) for m in members if m.embedding), 0)
    if dim == 0:
        return []
    acc = [0.0] * dim
    n = 0
    for m in members:
        if not m.embedding or len(m.embedding) != dim:
            continue
        for i, v in enumerate(m.embedding):
            acc[i] += v
        n += 1
    if n == 0:
        return acc
    return [v / n for v in acc]


def _dominant_emotion(members: List[MemoryEntry]) -> Optional[str]:
    counter: Counter[str] = Counter()
    for m in members:
        if not m.emotion_associations:
            continue
        # Pick the highest-weighted emotion in this memory
        try:
            best = max(m.emotion_associations.items(), key=lambda kv: kv[1])[0]
        except ValueError:
            continue
        counter[best] += 1
    if not counter:
        return None
    return counter.most_common(1)[0][0]


def _avg_confidence(members: List[MemoryEntry]) -> float:
    if not members:
        return 0.0
    return sum(m.confidence for m in members) / len(members)


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ---------------------------------------------------------------------------
# HDBSCAN backend
# ---------------------------------------------------------------------------


@dataclass
class HdbscanClusterer:
    """`IMemoryClusterer` over the `hdbscan` library.

    Distance metric: precomputed cosine distance (1 - cosine_similarity)
    so HDBSCAN's density logic operates in semantic space. We avoid
    relying on hdbscan's built-in metric='cosine' because some hdbscan
    versions don't support it for boruvka_kdtree.
    """

    min_cluster_size: int = 3
    min_samples: Optional[int] = None
    cluster_selection_epsilon: float = 0.0

    def cluster(
        self, entries: List[MemoryEntry], min_cluster_size: Optional[int] = None
    ) -> List[MemoryCluster]:
        try:
            import hdbscan
            import numpy as np
        except ImportError as e:
            raise ImportError(
                "hdbscan / numpy not installed; install hdbscan or use DensityFallbackClusterer"
            ) from e

        # Filter out memories without embeddings
        with_emb = [e for e in entries if e.embedding]
        if len(with_emb) < (min_cluster_size or self.min_cluster_size):
            logger.debug("hdbscan_too_few_entries", count=len(with_emb))
            return []

        size = min_cluster_size or self.min_cluster_size
        vectors = np.asarray([e.embedding for e in with_emb], dtype=float)

        # Precomputed cosine distance matrix
        norms = np.linalg.norm(vectors, axis=1)
        norms[norms == 0] = 1e-12
        unit = vectors / norms[:, None]
        sim = unit @ unit.T
        # numerical safety
        sim = np.clip(sim, -1.0, 1.0)
        dist = 1.0 - sim

        try:
            model = hdbscan.HDBSCAN(
                min_cluster_size=size,
                min_samples=self.min_samples,
                cluster_selection_epsilon=self.cluster_selection_epsilon,
                metric="precomputed",
            )
            labels = model.fit_predict(dist.astype(float))
        except Exception as exc:
            logger.warning("hdbscan_fit_failed", error=str(exc))
            return []

        return _build_clusters_from_labels(with_emb, list(labels))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "hdbscan",
            "min_cluster_size": self.min_cluster_size,
            "min_samples": self.min_samples,
            "cluster_selection_epsilon": self.cluster_selection_epsilon,
        }


# ---------------------------------------------------------------------------
# Fallback: connected components in cosine-similarity threshold graph
# ---------------------------------------------------------------------------


@dataclass
class DensityFallbackClusterer:
    """Pure-Python clusterer for environments without hdbscan.

    Algorithm:
      1. For every pair (i, j), edge if cosine_similarity ≥ similarity_threshold.
      2. Connected components → clusters.
      3. Drop components smaller than `min_cluster_size`.

    Best for ≤ a few hundred memories. O(N²) similarity computations.
    """

    similarity_threshold: float = 0.7
    min_cluster_size: int = 3

    def cluster(
        self, entries: List[MemoryEntry], min_cluster_size: Optional[int] = None
    ) -> List[MemoryCluster]:
        size = min_cluster_size or self.min_cluster_size
        with_emb = [e for e in entries if e.embedding]
        n = len(with_emb)
        if n < size:
            return []

        # Union-Find
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for i in range(n):
            for j in range(i + 1, n):
                if _cosine(with_emb[i].embedding, with_emb[j].embedding) >= self.similarity_threshold:
                    union(i, j)

        # Group members by root
        groups: Dict[int, List[int]] = {}
        for i in range(n):
            groups.setdefault(find(i), []).append(i)

        # Build clusters with stable ids
        clusters: List[MemoryCluster] = []
        next_id = 0
        for _, idxs in sorted(groups.items()):
            if len(idxs) < size:
                continue
            members = [with_emb[i] for i in idxs]
            clusters.append(
                MemoryCluster(
                    id=next_id,
                    member_ids=[m.id for m in members],
                    members=members,
                    centroid=_mean_embedding(members),
                    dominant_emotion=_dominant_emotion(members),
                    avg_confidence=_avg_confidence(members),
                )
            )
            next_id += 1
        return clusters

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "density_fallback",
            "similarity_threshold": self.similarity_threshold,
            "min_cluster_size": self.min_cluster_size,
        }


# ---------------------------------------------------------------------------
# Internal: shared label → cluster builder
# ---------------------------------------------------------------------------


def _build_clusters_from_labels(
    entries: List[MemoryEntry], labels: List[int]
) -> List[MemoryCluster]:
    if len(entries) != len(labels):
        return []
    by_label: Dict[int, List[MemoryEntry]] = {}
    for label, e in zip(labels, entries):
        if label < 0:
            continue  # noise
        by_label.setdefault(label, []).append(e)

    clusters: List[MemoryCluster] = []
    for new_id, (_, members) in enumerate(sorted(by_label.items())):
        clusters.append(
            MemoryCluster(
                id=new_id,
                member_ids=[m.id for m in members],
                members=members,
                centroid=_mean_embedding(members),
                dominant_emotion=_dominant_emotion(members),
                avg_confidence=_avg_confidence(members),
            )
        )
    return clusters


__all__ = [
    "DensityFallbackClusterer",
    "HdbscanClusterer",
    "IMemoryClusterer",
    "MemoryCluster",
]
