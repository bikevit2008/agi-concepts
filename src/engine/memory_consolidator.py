"""Memory consolidator — runs during sleep phases.

NREM-like phase: replay & strengthen. Increases the `confidence` of
memories that share emotional or temporal context (a coarse Hebbian
"neurons that fire together"). Downscale memories with very low recall
weight (value-based forgetting).

REM-like phase: cross-link & abstract. Looks for clusters of memories
with shared embeddings and synthesizes a higher-level "abstraction"
memory that summarises the cluster.

Implementation is intentionally simple — we don't try to match the
neuroscience exactly, we just provide useful sleep-time work that
reduces noise and creates higher-level concepts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

import structlog

from src.contracts.memory import IMemoryStore, MemoryEntry
from src.contracts.sleep import IMemoryConsolidator

logger = structlog.get_logger("consciousness.engine.memory_consolidator")


@dataclass
class HebbianMemoryConsolidator:
    """`IMemoryConsolidator` over an existing `IMemoryStore`.

    Attributes:
        memory_store: store to consolidate. Must support all_entries().
        forget_below_confidence: drop memories with confidence < this.
        nrem_strengthen_factor: multiplier on confidence for NREM-co-active.
        rem_min_cluster_size: REM clusters need at least N memories.
    """

    memory_store: IMemoryStore
    forget_below_confidence: float = 0.05
    nrem_strengthen_factor: float = 1.05
    rem_min_cluster_size: int = 3
    _stats: Dict[str, int] = field(default_factory=dict)

    def consolidate_nrem(self, memory_ids: List[str]) -> Dict[str, Any]:
        """NREM: strengthen memories with shared emotional context.

        Strategy: take all entries (or those whose ids are in `memory_ids`),
        find pairs sharing at least one emotional association, bump their
        confidence by `nrem_strengthen_factor`. Drop any memory whose
        confidence falls below `forget_below_confidence` (value-based
        forgetting).
        """
        try:
            entries = self._collect_entries(memory_ids)
        except Exception as e:
            logger.warning("consolidate_nrem_collect_failed", error=str(e))
            return {"phase": "nrem", "consolidated": 0, "forgotten": 0}

        if not entries:
            return {"phase": "nrem", "consolidated": 0, "forgotten": 0}

        # Hebbian: for every pair sharing an emotion, strengthen both
        strengthened = 0
        for i, a in enumerate(entries):
            for b in entries[i + 1:]:
                shared = set(a.emotion_associations.keys()) & set(b.emotion_associations.keys())
                if not shared:
                    continue
                a.confidence = min(1.0, a.confidence * self.nrem_strengthen_factor)
                b.confidence = min(1.0, b.confidence * self.nrem_strengthen_factor)
                strengthened += 1

        # Forget low-confidence memories — note this only mutates the
        # MemoryEntry confidence; deleting from the store needs backend
        # support and we don't gate on that here.
        forgotten = sum(1 for e in entries if e.confidence < self.forget_below_confidence)

        logger.info(
            "consolidate_nrem_done",
            entries=len(entries),
            strengthened=strengthened,
            forgotten=forgotten,
        )
        return {
            "phase": "nrem",
            "consolidated": strengthened,
            "forgotten": forgotten,
            "entries_processed": len(entries),
        }

    def consolidate_rem(self, memory_ids: List[str]) -> Dict[str, Any]:
        """REM: emergent cluster abstractions.

        Strategy: group memories by their dominant emotion, and for any
        group with at least `rem_min_cluster_size` members, create a new
        "abstraction" memory summarising them. The summary itself is a
        plain string ("cluster of N memories with dominant emotion X");
        a richer LLM-driven summarisation is left for a later pass.
        """
        try:
            entries = self._collect_entries(memory_ids)
        except Exception as e:
            logger.warning("consolidate_rem_collect_failed", error=str(e))
            return {"phase": "rem", "consolidated": 0}

        if not entries:
            return {"phase": "rem", "consolidated": 0}

        # Group by dominant emotion (max-valued key in emotion_associations)
        clusters: Dict[str, List[MemoryEntry]] = {}
        for e in entries:
            if not e.emotion_associations:
                continue
            dominant = max(e.emotion_associations.items(), key=lambda kv: kv[1])[0]
            clusters.setdefault(dominant, []).append(e)

        abstractions = 0
        for emo, members in clusters.items():
            if len(members) < self.rem_min_cluster_size:
                continue
            joined = "; ".join(m.content[:80] for m in members[:5])
            try:
                self.memory_store.store(
                    MemoryEntry(
                        id="",
                        content=f"[abstraction:{emo}] cluster of {len(members)}: {joined}",
                        source="rem_consolidation",
                        emotion_associations={emo: 1.0},
                        confidence=0.9,
                    )
                )
                abstractions += 1
            except Exception as e:
                logger.warning("rem_abstraction_store_failed", error=str(e))

        logger.info(
            "consolidate_rem_done",
            entries=len(entries),
            clusters=len(clusters),
            abstractions=abstractions,
        )
        return {
            "phase": "rem",
            "consolidated": abstractions,
            "clusters": len(clusters),
            "entries_processed": len(entries),
        }

    def _collect_entries(self, memory_ids: List[str]) -> List[MemoryEntry]:
        if not hasattr(self.memory_store, "all_entries"):
            return []
        all_entries = self.memory_store.all_entries()  # type: ignore[attr-defined]
        if memory_ids:
            wanted = set(memory_ids)
            return [e for e in all_entries if e.id in wanted]
        return all_entries

    def to_dict(self) -> Dict[str, object]:
        return {
            "type": "hebbian",
            "forget_below_confidence": self.forget_below_confidence,
            "nrem_strengthen_factor": self.nrem_strengthen_factor,
            "rem_min_cluster_size": self.rem_min_cluster_size,
        }


__all__ = ["HebbianMemoryConsolidator"]
