"""Learning contracts for lightweight self-learning context.

Inspired by Agno's LearningMachine stores, but intentionally narrower: this
layer captures session continuity and durable insights without replacing the
existing memory/provenance/goal architecture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


def _list_or_empty(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _int_or_default(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_or_default(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass
class SessionContext:
    """Compact continuation state for the current consciousness session."""

    session_id: str = "default"
    summary: str = ""
    current_goal: Optional[str] = None
    current_plan: List[str] = field(default_factory=list)
    progress: str = ""
    last_intent: str = ""
    last_response: str = ""
    interaction_count: int = 0
    updated_tick: int = 0
    recent_events: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "summary": self.summary,
            "current_goal": self.current_goal,
            "current_plan": list(self.current_plan),
            "progress": self.progress,
            "last_intent": self.last_intent,
            "last_response": self.last_response,
            "interaction_count": self.interaction_count,
            "updated_tick": self.updated_tick,
            "recent_events": list(self.recent_events),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionContext":
        return cls(
            session_id=str(data.get("session_id") or "default"),
            summary=str(data.get("summary") or ""),
            current_goal=(
                str(data["current_goal"])
                if data.get("current_goal") not in (None, "")
                else None
            ),
            current_plan=[
                str(item) for item in _list_or_empty(data.get("current_plan"))
            ],
            progress=str(data.get("progress") or ""),
            last_intent=str(data.get("last_intent") or ""),
            last_response=str(data.get("last_response") or ""),
            interaction_count=_int_or_default(data.get("interaction_count"), 0),
            updated_tick=_int_or_default(data.get("updated_tick"), 0),
            recent_events=[
                dict(item)
                for item in _list_or_empty(data.get("recent_events"))
                if isinstance(item, dict)
            ],
        )


@dataclass
class LearnedInsight:
    """Reusable insight extracted from reflection or goal progress."""

    id: str
    title: str
    learning: str
    context: str = ""
    source: str = "system"
    created_tick: int = 0
    last_used_tick: int = 0
    confidence: float = 0.6
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "learning": self.learning,
            "context": self.context,
            "source": self.source,
            "created_tick": self.created_tick,
            "last_used_tick": self.last_used_tick,
            "confidence": self.confidence,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LearnedInsight":
        return cls(
            id=str(data.get("id") or ""),
            title=str(data.get("title") or ""),
            learning=str(data.get("learning") or ""),
            context=str(data.get("context") or ""),
            source=str(data.get("source") or "system"),
            created_tick=_int_or_default(data.get("created_tick"), 0),
            last_used_tick=_int_or_default(data.get("last_used_tick"), 0),
            confidence=_float_or_default(data.get("confidence"), 0.6),
            tags=[str(item) for item in _list_or_empty(data.get("tags"))],
            metadata=(
                dict(data.get("metadata"))
                if isinstance(data.get("metadata"), dict)
                else {}
            ),
        )


@runtime_checkable
class ILearningStore(Protocol):
    """Stores session context and reusable learned insights."""

    def record_interaction(
        self,
        tick: int,
        stimulus: str,
        result: Dict[str, Any],
        current_goal: Optional[Dict[str, Any]] = None,
    ) -> SessionContext:
        """Update session context from a processed stimulus."""
        ...

    def record_reflection(
        self,
        tick: int,
        reflection: Dict[str, Any],
    ) -> Optional[LearnedInsight]:
        """Capture a reusable insight from reflection output."""
        ...

    def recall(self, query: str, limit: int = 5) -> List[LearnedInsight]:
        """Return relevant learned insights for a query."""
        ...

    def context(self, query: str = "", limit: int = 3) -> Dict[str, Any]:
        """Return compact prompt context."""
        ...

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for checkpointing."""
        ...

    def restore(self, data: Any) -> None:
        """Restore from checkpoint data."""
        ...


class NullLearningStore:
    """No-op learning store used when self-learning is disabled."""

    def record_interaction(
        self,
        tick: int,
        stimulus: str,
        result: Dict[str, Any],
        current_goal: Optional[Dict[str, Any]] = None,
    ) -> SessionContext:
        return SessionContext()

    def record_reflection(
        self,
        tick: int,
        reflection: Dict[str, Any],
    ) -> Optional[LearnedInsight]:
        return None

    def recall(self, query: str, limit: int = 5) -> List[LearnedInsight]:
        return []

    def context(self, query: str = "", limit: int = 3) -> Dict[str, Any]:
        return {
            "type": "null",
            "session_context": SessionContext().to_dict(),
            "learned_insights": [],
            "insight_count": 0,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "null",
            "session_context": SessionContext().to_dict(),
            "learned_insights": [],
            "insight_count": 0,
        }

    def restore(self, data: Any) -> None:
        return None


__all__ = [
    "ILearningStore",
    "LearnedInsight",
    "NullLearningStore",
    "SessionContext",
]
