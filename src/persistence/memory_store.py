"""Memory stores — IMemoryStore implementations.

Two backends:

1. InMemoryMemoryStore — pure Python list + cosine similarity. No
   external deps. Used for tests and as a fallback when LanceDB is
   not available.

2. LanceDbMemoryStore — production. Persists to disk via LanceDB,
   supports proper vector search. Schema (Pydantic model not used —
   PyArrow schema for portability):

       id           string
       content      string
       vector       list<float32>[D]   (D = embedder.dimension)
       source       string
       timestamp_ms int64
       confidence   float32
       emotion_json string             (JSON-encoded dict)

Both stores use the same `IEmbedder` to produce vectors at write/query
time, so they are interchangeable.
"""

from __future__ import annotations

import json
import math
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from src.contracts.memory import (
    MemoryEntry,
    ProvenanceVerdict,
    RecalledMemory,
)
from src.persistence.embedder import IEmbedder

logger = structlog.get_logger("consciousness.persistence.memory")


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _verdict_for_similarity(
    sim: float,
    real_threshold: float,
    uncertain_threshold: float,
) -> ProvenanceVerdict:
    if sim >= real_threshold:
        return ProvenanceVerdict.REAL
    if sim >= uncertain_threshold:
        return ProvenanceVerdict.UNCERTAIN
    return ProvenanceVerdict.HALLUCINATED


# ---------------------------------------------------------------------------
# InMemoryMemoryStore
# ---------------------------------------------------------------------------


class InMemoryMemoryStore:
    """List-based store with cosine similarity. Always works."""

    def __init__(
        self,
        embedder: IEmbedder,
        real_threshold: float = 0.85,
        uncertain_threshold: float = 0.65,
    ) -> None:
        self._embedder = embedder
        self._entries: List[MemoryEntry] = []
        self._real_threshold = real_threshold
        self._uncertain_threshold = uncertain_threshold

    def store(self, entry: MemoryEntry) -> str:
        if not entry.id:
            entry.id = uuid.uuid4().hex
        if entry.embedding is None:
            entry.embedding = self._embedder.embed(entry.content)
        if entry.timestamp_ms <= 0:
            entry.timestamp_ms = int(time.time() * 1000)
        self._entries.append(entry)
        return entry.id

    def retrieve(
        self,
        query: str,
        limit: int = 5,
        min_similarity: float = 0.0,
        emotion_filter: Optional[Dict[str, float]] = None,
    ) -> List[RecalledMemory]:
        if not self._entries:
            return []
        q_vec = self._embedder.embed(query)
        scored: List[RecalledMemory] = []
        for e in self._entries:
            if e.embedding is None:
                continue
            sim = _cosine_similarity(q_vec, e.embedding)
            if sim < min_similarity:
                continue
            if emotion_filter:
                # require at least one emotion association ≥ given threshold
                ok = any(
                    e.emotion_associations.get(emo, 0.0) >= thr
                    for emo, thr in emotion_filter.items()
                )
                if not ok:
                    continue
            scored.append(
                RecalledMemory(
                    entry=e,
                    similarity=sim,
                    verdict=_verdict_for_similarity(
                        sim, self._real_threshold, self._uncertain_threshold
                    ),
                )
            )
        scored.sort(key=lambda r: r.similarity, reverse=True)
        return scored[:limit]

    def count(self) -> int:
        return len(self._entries)

    def all_contents(self) -> List[str]:
        return [e.content for e in self._entries]

    def all_entries(self) -> List[MemoryEntry]:
        return list(self._entries)

    def close(self) -> None:
        return None


# ---------------------------------------------------------------------------
# LanceDbMemoryStore
# ---------------------------------------------------------------------------


class LanceDbMemoryStore:
    """LanceDB-backed memory store. Persistent, scalable.

    Lazy-imports lancedb so the rest of the system works without it.
    On any LanceDB error we log + degrade silently — the loop continues.
    """

    TABLE_SCHEMA_FIELDS = {
        "id": "string",
        "content": "string",
        "vector": "fixed-size-list",
        "source": "string",
        "timestamp_ms": "int64",
        "confidence": "float32",
        "emotion_json": "string",
    }

    def __init__(
        self,
        uri: str,
        table_name: str,
        embedder: IEmbedder,
        real_threshold: float = 0.85,
        uncertain_threshold: float = 0.65,
    ) -> None:
        try:
            import lancedb  # noqa: F401
            import pyarrow as pa  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "lancedb is not installed. Install with `pip install lancedb` "
                "or use InMemoryMemoryStore."
            ) from e

        self._embedder = embedder
        self._real_threshold = real_threshold
        self._uncertain_threshold = uncertain_threshold
        self._uri = uri
        self._table_name = table_name
        Path(uri).mkdir(parents=True, exist_ok=True)

        self._db = self._connect(uri)
        self._table = self._open_or_create_table(table_name, embedder.dimension)

    @staticmethod
    def _connect(uri: str):
        import lancedb

        return lancedb.connect(uri)

    def _open_or_create_table(self, table_name: str, dim: int):
        import pyarrow as pa

        schema = pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("content", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), list_size=dim)),
                pa.field("source", pa.string()),
                pa.field("timestamp_ms", pa.int64()),
                pa.field("confidence", pa.float32()),
                pa.field("emotion_json", pa.string()),
            ]
        )
        # Use the new list_tables() API; fall back to table_names() for
        # older lancedb versions that don't have it yet.
        try:
            existing = list(self._db.list_tables())
        except AttributeError:
            existing = list(self._db.table_names())
        if table_name in existing:
            return self._db.open_table(table_name)
        # Race-tolerant create: fall back to open if another writer beat us.
        try:
            return self._db.create_table(table_name, schema=schema, mode="create")
        except ValueError:
            return self._db.open_table(table_name)

    def store(self, entry: MemoryEntry) -> str:
        if not entry.id:
            entry.id = uuid.uuid4().hex
        if entry.embedding is None:
            entry.embedding = self._embedder.embed(entry.content)
        if entry.timestamp_ms <= 0:
            entry.timestamp_ms = int(time.time() * 1000)
        try:
            self._table.add(
                [
                    {
                        "id": entry.id,
                        "content": entry.content,
                        "vector": [float(x) for x in entry.embedding],
                        "source": entry.source,
                        "timestamp_ms": int(entry.timestamp_ms),
                        "confidence": float(entry.confidence),
                        "emotion_json": json.dumps(
                            entry.emotion_associations, ensure_ascii=False
                        ),
                    }
                ]
            )
        except Exception as e:
            logger.error("lancedb_store_failed", error=str(e), entry_id=entry.id)
        return entry.id

    def retrieve(
        self,
        query: str,
        limit: int = 5,
        min_similarity: float = 0.0,
        emotion_filter: Optional[Dict[str, float]] = None,
    ) -> List[RecalledMemory]:
        if self.count() == 0:
            return []
        q_vec = self._embedder.embed(query)
        try:
            results = self._table.search(q_vec).limit(max(limit, 1)).to_list()
        except Exception as e:
            logger.error("lancedb_retrieve_failed", error=str(e))
            return []

        out: List[RecalledMemory] = []
        for row in results:
            # _distance is L2 by default; we'd like cosine. Normalize at write+
            # read time, then sim = 1 - 0.5 * dist^2 (for unit vectors).
            try:
                vec = list(row.get("vector") or [])
                sim = _cosine_similarity(q_vec, vec)
            except Exception:
                sim = 0.0
            if sim < min_similarity:
                continue

            try:
                emo = json.loads(row.get("emotion_json") or "{}")
            except json.JSONDecodeError:
                emo = {}
            if emotion_filter and not any(
                emo.get(k, 0.0) >= v for k, v in emotion_filter.items()
            ):
                continue

            entry = MemoryEntry(
                id=str(row.get("id", "")),
                content=str(row.get("content", "")),
                embedding=vec,
                source=str(row.get("source", "unknown")),
                timestamp_ms=int(row.get("timestamp_ms", 0) or 0),
                emotion_associations=emo,
                confidence=float(row.get("confidence", 1.0) or 1.0),
            )
            out.append(
                RecalledMemory(
                    entry=entry,
                    similarity=sim,
                    verdict=_verdict_for_similarity(
                        sim, self._real_threshold, self._uncertain_threshold
                    ),
                )
            )
        out.sort(key=lambda r: r.similarity, reverse=True)
        return out[:limit]

    def count(self) -> int:
        try:
            return int(self._table.count_rows())
        except Exception as e:
            logger.warning("lancedb_count_failed", error=str(e))
            return 0

    def _to_records(self) -> List[Dict[str, Any]]:
        """Return all rows as a list of dicts. Uses pyarrow directly so
        we don't depend on pandas (which lancedb itself doesn't require)."""
        try:
            arrow_table = self._table.to_arrow()
        except Exception as e:
            logger.warning("lancedb_to_arrow_failed", error=str(e))
            return []
        try:
            return arrow_table.to_pylist()
        except Exception as e:
            logger.warning("lancedb_arrow_to_pylist_failed", error=str(e))
            return []

    def all_contents(self) -> List[str]:
        records = self._to_records()
        return [str(r.get("content", "")) for r in records]

    def all_entries(self) -> List[MemoryEntry]:
        out: List[MemoryEntry] = []
        for r in self._to_records():
            try:
                emo = json.loads(r.get("emotion_json") or "{}")
            except (json.JSONDecodeError, TypeError):
                emo = {}
            out.append(
                MemoryEntry(
                    id=str(r.get("id", "")),
                    content=str(r.get("content", "")),
                    embedding=list(r.get("vector") or []),
                    source=str(r.get("source", "unknown")),
                    timestamp_ms=int(r.get("timestamp_ms", 0) or 0),
                    emotion_associations=emo,
                    confidence=float(r.get("confidence", 1.0) or 1.0),
                )
            )
        return out

    def close(self) -> None:
        # LanceDB tables are file-backed; nothing to flush explicitly.
        return None


__all__ = ["InMemoryMemoryStore", "LanceDbMemoryStore"]
