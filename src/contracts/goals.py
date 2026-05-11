"""Goal contracts — persistent intentions for agentic behavior.

The goal layer is intentionally small: it stores durable intentions that
survive ticks and checkpoints, but it does not decide policy by itself. The
loop and agents can ask for the top active goal, report progress, and restore
the stack from snapshots. Concrete implementations live in ``src.engine``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


def _int_or_default(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _int_or_none(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class GoalStatus(str, Enum):
    """Lifecycle state for a persistent goal."""

    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


@dataclass
class Goal:
    """A durable intention owned by the consciousness loop."""

    id: str
    description: str
    priority: float = 0.5
    status: GoalStatus = GoalStatus.ACTIVE
    created_tick: int = 0
    last_pursued_tick: int = 0
    source: str = "system"
    deadline_tick: Optional[int] = None
    failure_count: int = 0
    success_count: int = 0
    notes: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "priority": self.priority,
            "status": self.status.value,
            "created_tick": self.created_tick,
            "last_pursued_tick": self.last_pursued_tick,
            "source": self.source,
            "deadline_tick": self.deadline_tick,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "notes": list(self.notes),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Goal":
        status_raw = data.get("status", GoalStatus.ACTIVE.value)
        try:
            status = GoalStatus(status_raw)
        except ValueError:
            status = GoalStatus.ACTIVE
        return cls(
            id=str(data.get("id", "")),
            description=str(data.get("description", "")),
            priority=float(data.get("priority", 0.5) or 0.5),
            status=status,
            created_tick=_int_or_default(data.get("created_tick"), 0),
            last_pursued_tick=_int_or_default(data.get("last_pursued_tick"), 0),
            source=str(data.get("source", "system")),
            deadline_tick=_int_or_none(data.get("deadline_tick")),
            failure_count=_int_or_default(data.get("failure_count"), 0),
            success_count=_int_or_default(data.get("success_count"), 0),
            notes=list(data.get("notes") or []),
            metadata=dict(data.get("metadata") or {}),
        )


@runtime_checkable
class IGoalStack(Protocol):
    """Persistent goal stack interface used by the loop and team."""

    def propose(
        self,
        description: str,
        priority: float,
        tick: int,
        source: str = "system",
        deadline_tick: Optional[int] = None,
    ) -> Optional[Goal]:
        """Create and push a new goal if capacity and dedup rules allow it."""
        ...

    def push(self, goal: Goal) -> bool:
        """Push an already-constructed goal."""
        ...

    def top_active(self) -> Optional[Goal]:
        """Return the highest-priority active goal, if any."""
        ...

    def active_goals(self, limit: int = 5) -> List[Goal]:
        """Return active goals ordered by priority."""
        ...

    def mark_progress(self, goal_id: str, tick: int, note: str = "") -> bool:
        """Record progress toward a goal."""
        ...

    def mark_blocked(self, goal_id: str, tick: int, reason: str = "") -> bool:
        """Record failed progress and possibly mark the goal blocked."""
        ...

    def complete(self, goal_id: str, tick: int, note: str = "") -> bool:
        """Mark a goal completed."""
        ...

    def abandon(self, goal_id: str, tick: int, reason: str = "") -> bool:
        """Mark a goal abandoned."""
        ...

    def refresh(
        self,
        tick: int,
        runtime_state: Dict[str, Any],
        hysteresis_state: Dict[str, float],
    ) -> List[Goal]:
        """Apply lifecycle rules such as stale/deadline/pressure checks."""
        ...

    def context(self, limit: int = 3) -> List[Dict[str, Any]]:
        """Return compact prompt context for agents."""
        ...

    def to_dict(self) -> Dict[str, Any]:
        """Serialize full stack for checkpointing."""
        ...

    def restore(self, data: Any) -> None:
        """Restore full stack from a serialized representation."""
        ...


class NullGoalStack:
    """No-op goal stack used when persistent intentions are disabled."""

    def propose(
        self,
        description: str,
        priority: float,
        tick: int,
        source: str = "system",
        deadline_tick: Optional[int] = None,
    ) -> Optional[Goal]:
        return None

    def push(self, goal: Goal) -> bool:
        return False

    def top_active(self) -> Optional[Goal]:
        return None

    def active_goals(self, limit: int = 5) -> List[Goal]:
        return []

    def mark_progress(self, goal_id: str, tick: int, note: str = "") -> bool:
        return False

    def mark_blocked(self, goal_id: str, tick: int, reason: str = "") -> bool:
        return False

    def complete(self, goal_id: str, tick: int, note: str = "") -> bool:
        return False

    def abandon(self, goal_id: str, tick: int, reason: str = "") -> bool:
        return False

    def refresh(
        self,
        tick: int,
        runtime_state: Dict[str, Any],
        hysteresis_state: Dict[str, float],
    ) -> List[Goal]:
        return []

    def context(self, limit: int = 3) -> List[Dict[str, Any]]:
        return []

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "null", "goals": []}

    def restore(self, data: Any) -> None:
        return None


__all__ = ["Goal", "GoalStatus", "IGoalStack", "NullGoalStack"]
