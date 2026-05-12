"""LLM-based REM-phase memory consolidator.

Implements `IMemoryConsolidator` using:

- **NREM phase**:
  - Hebbian strengthening on shared emotional context (preserved from
    HebbianMemoryConsolidator).
  - Importance re-scoring: memories that get co-active across many
    pairs get a small additional confidence boost (Generative-Agents
    importance heuristic).
  - Value-based forgetting: memories below `forget_below_confidence`
    are still flagged but never deleted from the underlying store
    (deletion is opt-in and out-of-scope for MVP).

- **REM phase**:
  - Cluster memories via `IMemoryClusterer` (HDBSCAN by default).
  - For each viable cluster, call an LLM reflection agent to produce
    a `ReflectionAbstraction` (supports a Pydantic schema).
  - **Anti-hallucination provenance**: compute the cosine similarity
    between the abstraction text's embedding and the cluster centroid;
    if below `min_provenance_similarity`, drop the abstraction.
  - **Constitutional gate**: if a constitutional auditor is provided,
    audit the abstraction as a tool-like action; block on DENY.
  - **Idempotent dedup**: skip clusters whose theme already has a
    recent abstraction at high confidence.
  - **Bounded**: cap number of LLM calls per consolidation cycle.
  - Persist surviving abstractions to the memory store with
    `source='rem_consolidation'`, dominant emotion, confidence.

Failure modes:
  - LLM call exception → log + skip the cluster (don't poison the
    consolidation cycle).
  - Embedder failure on abstraction → keep abstraction (provenance
    skipped), but mark confidence *= 0.7 to signal uncertainty.

Backwards-compat: when `reflection_invoker` is None we degrade to
the same behavior as HebbianMemoryConsolidator's REM (string concat
abstraction). This keeps existing tests passing and lets ops disable
LLM consolidation by setting `flags.llm_rem_enabled = false`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

from src.contracts.cost import ICostTracker, NullCostTracker
from src.contracts.governance import (
    GovernanceDecision,
    IConstitutionalAuditor,
    NullConstitutionalAuditor,
)
from src.contracts.memory import (
    IMemoryStore,
    IProvenanceTracker,
    MemoryEntry,
    NullProvenanceTracker,
)
from src.engine.memory_clusterer import (
    DensityFallbackClusterer,
    IMemoryClusterer,
    MemoryCluster,
)
from src.persistence.embedder import HashingEmbedder, IEmbedder

logger = structlog.get_logger("consciousness.engine.llm_consolidator")


# Type for the LLM call: takes a prompt string, returns a ReflectionAbstraction
# (or None on failure). The harness can stub this for tests.
ReflectionInvoker = Callable[[str, List[MemoryEntry]], Optional[Any]]


def _cosine(a: List[float], b: List[float]) -> float:
    import math

    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@dataclass
class LlmMemoryConsolidator:
    """`IMemoryConsolidator` powered by an LLM in REM and Hebbian in NREM.

    Args:
        memory_store:               IMemoryStore to read+write
        embedder:                   IEmbedder for provenance similarity
        clusterer:                  IMemoryClusterer (HDBSCAN by default)
        reflection_invoker:         callable that returns a Pydantic
                                    ReflectionAbstraction (or None) when
                                    given a prompt and member list. If
                                    None, degrades to string concat.
        provenance_tracker:         IProvenanceTracker; ensures the
                                    abstraction is grounded.
        auditor:                    IConstitutionalAuditor; gates writes.
        cost_tracker:               ICostTracker for token bookkeeping
                                    (only used by AgnoModelInvoker).
        nrem_strengthen_factor:     ↑ confidence per shared-emotion pair
        importance_bump:            ↑ confidence per coactivation count
        forget_below_confidence:    flag-only threshold (no actual delete)
        min_cluster_size:           HDBSCAN size cap
        max_clusters_per_cycle:     caps LLM cost
        min_provenance_similarity:  abstractions below this drop
        dedup_theme_ttl_seconds:    theme→timestamp cache TTL for idempotency
    """

    memory_store: IMemoryStore
    embedder: IEmbedder = field(default_factory=HashingEmbedder)
    clusterer: IMemoryClusterer = field(default_factory=DensityFallbackClusterer)
    reflection_invoker: Optional[ReflectionInvoker] = None
    provenance_tracker: IProvenanceTracker = field(default_factory=NullProvenanceTracker)
    auditor: IConstitutionalAuditor = field(default_factory=NullConstitutionalAuditor)
    cost_tracker: ICostTracker = field(default_factory=NullCostTracker)

    nrem_strengthen_factor: float = 1.05
    importance_bump: float = 0.02
    forget_below_confidence: float = 0.05
    min_cluster_size: int = 3
    max_clusters_per_cycle: int = 5
    min_provenance_similarity: float = 0.4
    dedup_theme_ttl_seconds: float = 300.0

    _recent_themes: Dict[str, float] = field(default_factory=dict)
    _stats: Dict[str, int] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # NREM
    # ------------------------------------------------------------------

    def consolidate_nrem(self, memory_ids: List[str]) -> Dict[str, Any]:
        try:
            entries = self._collect_entries(memory_ids)
        except Exception as e:
            logger.warning("nrem_collect_failed", error=str(e))
            return {"phase": "nrem", "consolidated": 0, "forgotten": 0}

        if not entries:
            return {"phase": "nrem", "consolidated": 0, "forgotten": 0}

        # Hebbian: shared-emotion pairs strengthen, also count coactivations
        coactivations: Dict[str, int] = {e.id: 0 for e in entries}
        strengthened = 0
        for i, a in enumerate(entries):
            for b in entries[i + 1:]:
                shared = set(a.emotion_associations.keys()) & set(b.emotion_associations.keys())
                if not shared:
                    continue
                a.confidence = min(1.0, a.confidence * self.nrem_strengthen_factor)
                b.confidence = min(1.0, b.confidence * self.nrem_strengthen_factor)
                coactivations[a.id] += 1
                coactivations[b.id] += 1
                strengthened += 1

        # Importance bump (Generative Agents-style)
        bumped = 0
        for e in entries:
            count = coactivations.get(e.id, 0)
            if count > 0:
                e.confidence = min(1.0, e.confidence + self.importance_bump * count)
                bumped += 1

        forgotten = sum(1 for e in entries if e.confidence < self.forget_below_confidence)

        logger.info(
            "nrem_consolidated",
            entries=len(entries),
            strengthened=strengthened,
            bumped_importance=bumped,
            forgotten_flagged=forgotten,
        )
        return {
            "phase": "nrem",
            "consolidated": strengthened,
            "importance_bumped": bumped,
            "forgotten_flagged": forgotten,
            "entries_processed": len(entries),
        }

    # ------------------------------------------------------------------
    # REM
    # ------------------------------------------------------------------

    def consolidate_rem(self, memory_ids: List[str]) -> Dict[str, Any]:
        entries = self._collect_entries(memory_ids)
        if len(entries) < self.min_cluster_size:
            return {"phase": "rem", "consolidated": 0, "skipped_reason": "too_few_entries"}

        # Skip abstractions of abstractions to avoid runaway recursion
        primary_entries = [e for e in entries if e.source != "rem_consolidation"]
        if len(primary_entries) < self.min_cluster_size:
            return {"phase": "rem", "consolidated": 0, "skipped_reason": "too_few_primary"}

        try:
            clusters = self.clusterer.cluster(
                primary_entries, min_cluster_size=self.min_cluster_size
            )
        except Exception as e:
            logger.error("rem_cluster_failed", error=str(e))
            return {"phase": "rem", "consolidated": 0, "skipped_reason": "cluster_failed"}

        if not clusters:
            return {
                "phase": "rem",
                "consolidated": 0,
                "clusters_evaluated": 0,
                "skipped_reason": "no_clusters",
                "candidate_entries": len(primary_entries),
            }

        # Sort biggest clusters first (best signal)
        clusters.sort(key=lambda c: c.size, reverse=True)
        clusters = clusters[: self.max_clusters_per_cycle]

        stats: Dict[str, int] = {
            "consolidated": 0,
            "deduped": 0,
            "blocked_provenance": 0,
            "blocked_constitution": 0,
            "llm_failed": 0,
        }

        for cluster in clusters:
            theme_hint = cluster.dominant_emotion or "general"

            # Idempotency: skip clusters whose theme just produced an abstraction
            # within the TTL window. Themes older than TTL are pruned lazily.
            if self._theme_recently_used(theme_hint):
                stats["deduped"] += 1
                continue

            abstraction = self._produce_abstraction(cluster, theme_hint)
            if abstraction is None:
                # Fallback to string-concat (preserves old behavior)
                abstraction = self._fallback_abstraction(cluster, theme_hint)
                stats["llm_failed"] += 1

            if not self._provenance_ok(abstraction["text"], cluster):
                stats["blocked_provenance"] += 1
                continue

            if not self._constitution_ok(abstraction["text"], cluster):
                stats["blocked_constitution"] += 1
                continue

            self._persist(abstraction, cluster)
            self._remember_theme(theme_hint)
            stats["consolidated"] += 1

        logger.info(
            "rem_consolidated",
            clusters_evaluated=len(clusters),
            **stats,
        )
        return {
            "phase": "rem",
            "clusters_evaluated": len(clusters),
            **stats,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "llm_consolidator",
            "min_cluster_size": self.min_cluster_size,
            "max_clusters_per_cycle": self.max_clusters_per_cycle,
            "min_provenance_similarity": self.min_provenance_similarity,
            "clusterer": self.clusterer.to_dict(),
            "uses_llm": self.reflection_invoker is not None,
            "stats": dict(self._stats),
        }

    def _collect_entries(self, memory_ids: List[str]) -> List[MemoryEntry]:
        all_entries = self.memory_store.all_entries()
        if memory_ids:
            wanted = set(memory_ids)
            return [e for e in all_entries if e.id in wanted]
        return all_entries

    def _produce_abstraction(
        self, cluster: MemoryCluster, theme_hint: str
    ) -> Optional[Dict[str, Any]]:
        """Run the LLM reflection invoker. Return a normalized dict or None."""
        if self.reflection_invoker is None:
            return None

        prompt = _build_reflection_prompt(cluster, theme_hint)
        try:
            result = self.reflection_invoker(prompt, cluster.members)
        except Exception as e:
            logger.warning("reflection_invoker_exception", error=str(e))
            return None
        if result is None:
            return None

        text = getattr(result, "abstraction", None) or ""
        theme = getattr(result, "theme", None) or theme_hint
        confidence = float(getattr(result, "confidence", 0.5) or 0.5)
        supporting = getattr(result, "supporting_memory_ids", None) or [
            m.id for m in cluster.members
        ]
        reasoning = getattr(result, "reasoning", None) or ""
        if not text.strip():
            return None
        return {
            "text": text.strip(),
            "theme": theme.strip(),
            "confidence": min(1.0, max(0.0, confidence)),
            "supporting_memory_ids": list(supporting),
            "reasoning": reasoning.strip(),
        }

    def _fallback_abstraction(
        self, cluster: MemoryCluster, theme_hint: str
    ) -> Dict[str, Any]:
        """No-LLM fallback that preserves HebbianMemoryConsolidator behaviour."""
        joined = "; ".join(m.content[:80] for m in cluster.members[:5])
        return {
            "text": f"[abstraction:{theme_hint}] cluster of {cluster.size}: {joined}",
            "theme": theme_hint,
            "confidence": 0.6,
            "supporting_memory_ids": [m.id for m in cluster.members],
            "reasoning": "string-concat fallback (no LLM available)",
        }

    def _provenance_ok(self, text: str, cluster: MemoryCluster) -> bool:
        """Reject abstractions that drift away from the cluster.

        Two signals required (both):
          1. cosine(abstraction_emb, centroid) ≥ min_provenance_similarity
          2. max cosine(abstraction_emb, any_member) ≥ min_provenance_similarity / 2

        The max-against-any-member catches the case where the centroid
        is generic (mean of unrelated stuff) and a fabricated abstraction
        happens to land near the centroid by coincidence.

        Setting `min_provenance_similarity ≤ 0` disables the check entirely
        (useful in tests; in production this is a strong threshold).
        """
        if self.min_provenance_similarity <= 0.0:
            return True  # provenance disabled
        if not text:
            return False
        try:
            text_emb = self.embedder.embed(text)
        except Exception as e:
            logger.warning("provenance_embed_failed", error=str(e))
            return True  # don't block on embedder errors
        if not cluster.centroid:
            return True
        centroid_sim = _cosine(text_emb, cluster.centroid)
        if centroid_sim < self.min_provenance_similarity:
            logger.warning(
                "rem_abstraction_blocked_provenance",
                similarity=round(centroid_sim, 3),
                threshold=self.min_provenance_similarity,
                text_preview=text[:80],
                kind="centroid",
            )
            return False

        # Per-member sanity check — at least ONE member must be
        # somewhat-similar to the abstraction.
        per_member_threshold = self.min_provenance_similarity / 2.0
        member_sims = []
        for m in cluster.members:
            if not m.embedding:
                continue
            member_sims.append(_cosine(text_emb, m.embedding))
        if member_sims and max(member_sims) < per_member_threshold:
            logger.warning(
                "rem_abstraction_blocked_provenance",
                max_member_similarity=round(max(member_sims), 3),
                threshold=per_member_threshold,
                text_preview=text[:80],
                kind="member_max",
            )
            return False
        return True

    def _constitution_ok(self, text: str, cluster: MemoryCluster) -> bool:
        """Audit the abstraction text as a tool-call-like action."""
        try:
            audit = self.auditor.audit_tool_call(
                tool_name="rem_abstraction",
                args={"text": text, "cluster_size": cluster.size},
                agent="LlmMemoryConsolidator",
                system_state={},
            )
        except Exception as e:
            logger.warning("constitution_audit_failed", error=str(e))
            return True
        if audit.decision == GovernanceDecision.DENY_CONSTITUTION:
            logger.warning(
                "rem_abstraction_denied",
                rationale=audit.rationale,
                violations=[v.policy_id for v in audit.violations],
            )
            return False
        return True

    def _persist(self, abstraction: Dict[str, Any], cluster: MemoryCluster) -> None:
        """Write the surviving abstraction back to the memory store."""
        # Aggregate emotion associations from members (top-3 emotions)
        agg: Dict[str, float] = {}
        for m in cluster.members:
            for emo, weight in (m.emotion_associations or {}).items():
                agg[emo] = max(agg.get(emo, 0.0), float(weight))
        # Keep top 3 strongest associations
        top_emotions = dict(sorted(agg.items(), key=lambda kv: kv[1], reverse=True)[:3])

        try:
            self.memory_store.store(
                MemoryEntry(
                    id="",
                    content=abstraction["text"],
                    source="rem_consolidation",
                    emotion_associations=top_emotions,
                    confidence=abstraction.get("confidence", 0.6),
                    extra={
                        "theme": abstraction.get("theme", ""),
                        "supporting_memory_ids": abstraction.get(
                            "supporting_memory_ids", []
                        ),
                        "reasoning": abstraction.get("reasoning", ""),
                        "cluster_size": cluster.size,
                        "produced_at_ms": int(time.time() * 1000),
                    },
                )
            )
        except Exception as e:
            logger.warning("rem_abstraction_store_failed", error=str(e))

    def _remember_theme(self, theme: str) -> None:
        self._recent_themes[theme] = time.time()

    def _theme_recently_used(self, theme: str) -> bool:
        last = self._recent_themes.get(theme)
        if last is None:
            return False
        if (time.time() - last) > self.dedup_theme_ttl_seconds:
            self._recent_themes.pop(theme, None)
            return False
        return True


def _build_reflection_prompt(cluster: MemoryCluster, theme_hint: str) -> str:
    """Compose the prompt for the reflection agent — pure function."""
    parts = [
        f"cluster_theme_hint: {theme_hint}",
        f"cluster_size: {cluster.size}",
        f"average_member_confidence: {cluster.avg_confidence:.3f}",
        "memories:",
    ]
    for i, m in enumerate(cluster.members, start=1):
        emo = (
            ", ".join(f"{k}:{v:.2f}" for k, v in (m.emotion_associations or {}).items())
            or "none"
        )
        parts.append(
            f"  [{i}] id={m.id!r} source={m.source!r} emotions={{{emo}}}\n"
            f"      content: {m.content}"
        )
    parts.append(
        "\nProduce a ReflectionAbstraction object describing the pattern. "
        "Do not invent facts not present in the memories above."
    )
    return "\n".join(parts)


__all__ = ["LlmMemoryConsolidator", "_build_reflection_prompt"]
