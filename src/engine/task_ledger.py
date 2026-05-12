"""Deterministic task ledger for goal pursuit.

The ledger keeps small actionable tasks separate from the higher-level goal
stack. It deliberately avoids LLM calls: Planning can suggest actions, while
the loop/ledger handle dedupe, dependencies, and checkpointing.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.contracts.tasks import Task, TaskStatus


TERMINAL_STATUSES = {TaskStatus.COMPLETED, TaskStatus.FAILED}
DEPENDENCY_SATISFIED_STATUSES = {TaskStatus.COMPLETED}


@dataclass
class PersistentTaskLedger:
    """Checkpointable task list with deterministic dedupe and dependency checks."""

    max_tasks: int = 200

    _tasks: Dict[str, Task] = field(default_factory=dict)
    _task_order: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.max_tasks = max(1, _int_or_default(self.max_tasks, 200))

    def create(
        self,
        title: str,
        tick: int,
        goal_id: Optional[str] = None,
        source: str = "system",
        dependencies: Optional[List[str]] = None,
    ) -> Optional[Task]:
        clean_title = " ".join(str(title or "").split())
        if not clean_title:
            return None
        duplicate = self._find_duplicate(clean_title, goal_id=goal_id)
        if duplicate:
            return duplicate
        task = Task(
            id=uuid.uuid4().hex[:10],
            title=clean_title[:240],
            goal_id=goal_id,
            created_tick=int(tick),
            updated_tick=int(tick),
            source=str(source or "system"),
            dependencies=[str(dep) for dep in (dependencies or [])],
        )
        if self._is_blocked(task):
            task.status = TaskStatus.BLOCKED
        self._tasks[task.id] = task
        self._task_order.append(task.id)
        self._prune()
        return task

    def update_status(
        self,
        task_id: str,
        status: TaskStatus | str,
        tick: int,
        note: str = "",
        result: str = "",
    ) -> Optional[Task]:
        task = self._tasks.get(str(task_id))
        if task is None:
            return None
        try:
            next_status = status if isinstance(status, TaskStatus) else TaskStatus(status)
        except ValueError:
            return None
        if next_status == TaskStatus.BLOCKED and not self._is_blocked(task):
            return None
        task.status = next_status
        task.updated_tick = int(tick)
        if note:
            task.notes.append(str(note)[:300])
            task.notes = task.notes[-8:]
        if result:
            task.result = str(result)[:500]
        self._refresh_blocked_statuses()
        return task

    def available_tasks(
        self,
        goal_id: Optional[str] = None,
        limit: int = 5,
    ) -> List[Task]:
        limit_n = max(0, _int_or_default(limit, 5))
        if limit_n == 0:
            return []
        self._refresh_blocked_statuses()
        available: List[Task] = []
        for task_id in self._task_order:
            task = self._tasks.get(task_id)
            if task is None or task.status != TaskStatus.PENDING:
                continue
            if goal_id and task.goal_id != goal_id:
                continue
            available.append(task)
            if len(available) >= limit_n:
                break
        return available

    def tasks(
        self,
        status: Optional[TaskStatus | str] = None,
        goal_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Task]:
        limit_n = max(0, _int_or_default(limit, 20))
        if limit_n == 0:
            return []
        status_filter: Optional[TaskStatus] = None
        if status is not None:
            try:
                status_filter = status if isinstance(status, TaskStatus) else TaskStatus(status)
            except ValueError:
                return []
        results: List[Task] = []
        for task_id in self._task_order:
            task = self._tasks.get(task_id)
            if task is None:
                continue
            if goal_id and task.goal_id != goal_id:
                continue
            if status_filter is not None and task.status != status_filter:
                continue
            results.append(task)
        return results[-limit_n:]

    def context(self, goal_id: Optional[str] = None, limit: int = 5) -> Dict[str, Any]:
        tasks = [
            task
            for task in (self._tasks.get(task_id) for task_id in self._task_order)
            if task is not None and (goal_id is None or task.goal_id == goal_id)
        ]
        counts: Dict[str, int] = {}
        for task in tasks:
            counts[task.status.value] = counts.get(task.status.value, 0) + 1
        recent = tasks[-max(0, _int_or_default(limit, 5)) :]
        return {
            "type": "persistent",
            "task_count": len(tasks),
            "counts": counts,
            "available": [
                task.to_dict() for task in self.available_tasks(goal_id=goal_id, limit=limit)
            ],
            "tasks": [task.to_dict() for task in recent],
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "persistent",
            "config": {"max_tasks": self.max_tasks},
            "task_count": len(self._tasks),
            "tasks": [
                self._tasks[task_id].to_dict()
                for task_id in self._task_order
                if task_id in self._tasks
            ],
        }

    def restore(self, data: Any) -> None:
        if not isinstance(data, dict):
            return
        config = data.get("config")
        if isinstance(config, dict):
            self.max_tasks = max(1, _int_or_default(config.get("max_tasks"), self.max_tasks))
        self._tasks = {}
        self._task_order = []
        raw_tasks = data.get("tasks")
        if isinstance(raw_tasks, list):
            for item in raw_tasks:
                if not isinstance(item, dict):
                    continue
                task = Task.from_dict(item)
                if not task.id or not task.title:
                    continue
                self._tasks[task.id] = task
                self._task_order.append(task.id)
        self._prune()
        self._refresh_blocked_statuses()

    def _find_duplicate(self, title: str, goal_id: Optional[str]) -> Optional[Task]:
        target = _normal_key(title)
        for task in self._tasks.values():
            if goal_id is not None and task.goal_id != goal_id:
                continue
            if task.status in TERMINAL_STATUSES:
                continue
            if _normal_key(task.title) == target:
                return task
        return None

    def _is_blocked(self, task: Task) -> bool:
        for dep_id in task.dependencies:
            dep = self._tasks.get(dep_id)
            if dep is None or dep.status not in DEPENDENCY_SATISFIED_STATUSES:
                return True
        return False

    def _refresh_blocked_statuses(self) -> None:
        for task in self._tasks.values():
            if task.status in TERMINAL_STATUSES or task.status == TaskStatus.IN_PROGRESS:
                continue
            task.status = TaskStatus.BLOCKED if self._is_blocked(task) else TaskStatus.PENDING

    def _prune(self) -> None:
        while len(self._task_order) > self.max_tasks:
            old_id = self._task_order.pop(0)
            self._tasks.pop(old_id, None)


def _normal_key(text: str) -> str:
    return " ".join(re.findall(r"[\w\-]+", text.lower()))


def _int_or_default(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


__all__ = ["PersistentTaskLedger"]
