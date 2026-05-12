"""Context provider contracts for deterministic external grounding."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Protocol, runtime_checkable


@dataclass
class ContextDocument:
    """A small piece of retrievable context."""

    id: str
    text: str
    name: str = ""
    uri: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "uri": self.uri,
            "text": self.text,
            "metadata": dict(self.metadata),
            "score": self.score,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextDocument":
        return cls(
            id=str(data.get("id") or ""),
            text=str(data.get("text") or ""),
            name=str(data.get("name") or ""),
            uri=str(data.get("uri") or ""),
            metadata=dict(data.get("metadata") or {}),
            score=float(data.get("score") or 0.0),
        )


@dataclass
class ContextAnswer:
    """Result from querying a context provider."""

    query: str
    documents: List[ContextDocument] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "documents": [document.to_dict() for document in self.documents],
            "text": self.text,
        }

    @property
    def text(self) -> str:
        return "\n\n".join(document.text for document in self.documents)


@runtime_checkable
class IContextProvider(Protocol):
    """Read-only provider that answers natural-language context queries."""

    @property
    def provider_id(self) -> str:
        """Stable identifier for this context source."""
        ...

    def query(self, query: str, limit: int = 5) -> ContextAnswer:
        """Return relevant documents for a query."""
        ...


class NullContextProvider:
    """No-op context provider."""

    @property
    def provider_id(self) -> str:
        return "null"

    def query(self, query: str, limit: int = 5) -> ContextAnswer:
        return ContextAnswer(query=str(query or ""), documents=[])


__all__ = [
    "ContextAnswer",
    "ContextDocument",
    "IContextProvider",
    "NullContextProvider",
]
