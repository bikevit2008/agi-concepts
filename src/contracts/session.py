"""Shared session-state contracts.

The shared session is the system's small blackboard: runtime, goals, learning,
agent outputs, and later task state share one checkpointable source of truth.
Agents only receive compact projections of this state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class SessionMutation:
    """Audit metadata for one shared-state mutation."""

    tick: int
    namespace: str
    source: str = "system"
    keys: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tick": self.tick,
            "namespace": self.namespace,
            "source": self.source,
            "keys": list(self.keys),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionMutation":
        keys = data.get("keys") if isinstance(data.get("keys"), list) else []
        return cls(
            tick=_int_or_default(data.get("tick"), 0),
            namespace=str(data.get("namespace") or ""),
            source=str(data.get("source") or "system"),
            keys=[str(key) for key in keys],
        )


@runtime_checkable
class ISharedSessionState(Protocol):
    """Checkpointable shared blackboard for loop/team/agent coordination."""

    def update_namespace(
        self,
        namespace: str,
        values: Dict[str, Any],
        tick: int = 0,
        source: str = "system",
        replace: bool = False,
    ) -> Dict[str, Any]:
        """Merge or replace a namespace and return the stored namespace."""
        ...

    def context(
        self,
        agent: str = "system",
        include_namespaces: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Return a compact projection safe to place in agent session_state."""
        ...

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for checkpointing."""
        ...

    def restore(self, data: Any) -> None:
        """Restore from checkpoint data."""
        ...


class NullSharedSessionState:
    """No-op shared session used when the blackboard is disabled."""

    def update_namespace(
        self,
        namespace: str,
        values: Dict[str, Any],
        tick: int = 0,
        source: str = "system",
        replace: bool = False,
    ) -> Dict[str, Any]:
        return {}

    def context(
        self,
        agent: str = "system",
        include_namespaces: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return {"type": "disabled", "session_id": "null"}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "null",
            "session_id": "null",
            "namespaces": {},
            "recent_mutations": [],
        }

    def restore(self, data: Any) -> None:
        return None


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "ISharedSessionState",
    "NullSharedSessionState",
    "SessionMutation",
]
