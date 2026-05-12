"""Task ledger contracts for durable goal decomposition."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


class TaskStatus(str, Enum):
    """Lifecycle state for a small goal-pursuit task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Task:
    """A checkpointable unit of work tied to a durable goal."""

    id: str
    title: str
    goal_id: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    created_tick: int = 0
    updated_tick: int = 0
    source: str = "system"
    dependencies: List[str] = field(default_factory=list)
    result: str = ""
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "goal_id": self.goal_id,
            "status": self.status.value,
            "created_tick": self.created_tick,
            "updated_tick": self.updated_tick,
            "source": self.source,
            "dependencies": list(self.dependencies),
            "result": self.result,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        status_raw = data.get("status", TaskStatus.PENDING.value)
        try:
            status = TaskStatus(status_raw)
        except ValueError:
            status = TaskStatus.PENDING
        deps = data.get("dependencies") if isinstance(data.get("dependencies"), list) else []
        notes = data.get("notes") if isinstance(data.get("notes"), list) else []
        return cls(
            id=str(data.get("id") or ""),
            title=str(data.get("title") or ""),
            goal_id=(
                str(data["goal_id"])
                if data.get("goal_id") not in (None, "")
                else None
            ),
            status=status,
            created_tick=_int_or_default(data.get("created_tick"), 0),
            updated_tick=_int_or_default(data.get("updated_tick"), 0),
            source=str(data.get("source") or "system"),
            dependencies=[str(dep) for dep in deps],
            result=str(data.get("result") or ""),
            notes=[str(note) for note in notes],
        )


@runtime_checkable
class ITaskLedger(Protocol):
    """Durable task list used by goal pursuit and agent prompts."""

    def create(
        self,
        title: str,
        tick: int,
        goal_id: Optional[str] = None,
        source: str = "system",
        dependencies: Optional[List[str]] = None,
    ) -> Optional[Task]:
        """Create a task unless it is a duplicate."""
        ...

    def update_status(
        self,
        task_id: str,
        status: TaskStatus | str,
        tick: int,
        note: str = "",
        result: str = "",
    ) -> Optional[Task]:
        """Update a task lifecycle status."""
        ...

    def available_tasks(
        self,
        goal_id: Optional[str] = None,
        limit: int = 5,
    ) -> List[Task]:
        """Return pending tasks whose dependencies are complete."""
        ...

    def tasks(
        self,
        status: Optional[TaskStatus | str] = None,
        goal_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Task]:
        """Return tasks filtered by status/goal."""
        ...

    def context(self, goal_id: Optional[str] = None, limit: int = 5) -> Dict[str, Any]:
        """Return compact prompt context."""
        ...

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for checkpointing."""
        ...

    def restore(self, data: Any) -> None:
        """Restore from checkpoint data."""
        ...


class NullTaskLedger:
    """No-op task ledger used when task decomposition is disabled."""

    def create(
        self,
        title: str,
        tick: int,
        goal_id: Optional[str] = None,
        source: str = "system",
        dependencies: Optional[List[str]] = None,
    ) -> Optional[Task]:
        return None

    def update_status(
        self,
        task_id: str,
        status: TaskStatus | str,
        tick: int,
        note: str = "",
        result: str = "",
    ) -> Optional[Task]:
        return None

    def available_tasks(
        self,
        goal_id: Optional[str] = None,
        limit: int = 5,
    ) -> List[Task]:
        return []

    def tasks(
        self,
        status: Optional[TaskStatus | str] = None,
        goal_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Task]:
        return []

    def context(self, goal_id: Optional[str] = None, limit: int = 5) -> Dict[str, Any]:
        return {"type": "disabled", "tasks": [], "task_count": 0}

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "null", "tasks": [], "task_count": 0}

    def restore(self, data: Any) -> None:
        return None


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


__all__ = ["ITaskLedger", "NullTaskLedger", "Task", "TaskStatus"]
