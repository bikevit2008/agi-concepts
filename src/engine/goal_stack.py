"""Persistent goal stack implementation.

Goals are the first minimal move from pure stimulus-response toward durable
agency: a reflection can create an intention, planning can report whether it
advanced that intention, and checkpoint/restore keeps it alive across process
restarts.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.contracts.goals import Goal, GoalStatus, IGoalStack


def _normalize_description(description: str) -> str:
    return " ".join(description.strip().lower().split())


def _clamp_priority(priority: float) -> float:
    return max(0.0, min(1.0, float(priority)))


@dataclass
class PersistentGoalStack:
    """In-memory durable intention stack with deterministic serialization."""

    max_active_goals: int = 5
    stale_after_ticks: int = 50
    block_after_failures: int = 3
    abandon_after_failures: int = 6
    pressure_stress_threshold: float = 0.9
    pressure_blocks_below_priority: float = 0.4
    _goals: List[Goal] = field(default_factory=list)

    def propose(
        self,
        description: str,
        priority: float,
        tick: int,
        source: str = "system",
        deadline_tick: Optional[int] = None,
    ) -> Optional[Goal]:
        description = description.strip()
        if not description:
            return None
        goal = Goal(
            id=self._make_id(description, tick, source),
            description=description,
            priority=_clamp_priority(priority),
            created_tick=tick,
            last_pursued_tick=tick,
            source=source,
            deadline_tick=deadline_tick,
        )
        return goal if self.push(goal) else None

    def push(self, goal: Goal) -> bool:
        goal.description = goal.description.strip()
        if not goal.id or not goal.description:
            return False
        goal.priority = _clamp_priority(goal.priority)

        normalized = _normalize_description(goal.description)
        for existing in self._goals:
            if _normalize_description(existing.description) != normalized:
                continue
            if existing.status in (GoalStatus.ACTIVE, GoalStatus.BLOCKED):
                return False

        if goal.status == GoalStatus.ACTIVE and len(self.active_goals()) >= self.max_active_goals:
            return False
        self._goals.append(goal)
        return True

    def top_active(self) -> Optional[Goal]:
        active = self.active_goals(limit=self.max_active_goals)
        return active[0] if active else None

    def active_goals(self, limit: int = 5) -> List[Goal]:
        active = [g for g in self._goals if g.status == GoalStatus.ACTIVE]
        active.sort(key=lambda g: (g.priority, -g.created_tick), reverse=True)
        return active[:limit]

    def mark_progress(self, goal_id: str, tick: int, note: str = "") -> bool:
        goal = self._find(goal_id)
        if goal is None:
            return False
        goal.status = GoalStatus.ACTIVE
        goal.last_pursued_tick = tick
        goal.success_count += 1
        goal.failure_count = max(0, goal.failure_count - 1)
        self._append_note(goal, tick, "progress", note)
        return True

    def mark_blocked(self, goal_id: str, tick: int, reason: str = "") -> bool:
        goal = self._find(goal_id)
        if goal is None or goal.status not in (GoalStatus.ACTIVE, GoalStatus.BLOCKED):
            return False
        goal.last_pursued_tick = tick
        goal.failure_count += 1
        if goal.failure_count >= self.abandon_after_failures:
            goal.status = GoalStatus.ABANDONED
            label = "abandoned"
        else:
            goal.status = GoalStatus.BLOCKED
            label = (
                "blocked"
                if goal.failure_count >= self.block_after_failures
                else "blocked_attempt"
            )
        self._append_note(goal, tick, label, reason)
        return True

    def complete(self, goal_id: str, tick: int, note: str = "") -> bool:
        goal = self._find(goal_id)
        if goal is None:
            return False
        goal.status = GoalStatus.COMPLETED
        goal.last_pursued_tick = tick
        goal.success_count += 1
        self._append_note(goal, tick, "completed", note)
        return True

    def abandon(self, goal_id: str, tick: int, reason: str = "") -> bool:
        goal = self._find(goal_id)
        if goal is None:
            return False
        goal.status = GoalStatus.ABANDONED
        goal.last_pursued_tick = tick
        self._append_note(goal, tick, "abandoned", reason)
        return True

    def refresh(
        self,
        tick: int,
        runtime_state: Dict[str, Any],
        hysteresis_state: Dict[str, float],
    ) -> List[Goal]:
        changed: List[Goal] = []
        stress = float(hysteresis_state.get("stress", 0.0) or 0.0)
        for goal in list(self._goals):
            if goal.status != GoalStatus.ACTIVE:
                continue
            if goal.deadline_tick is not None and tick > goal.deadline_tick:
                if self.abandon(goal.id, tick, "deadline exceeded"):
                    changed.append(goal)
                continue
            if tick - goal.last_pursued_tick > self.stale_after_ticks:
                if self.mark_blocked(goal.id, tick, "stale without progress"):
                    changed.append(goal)
                continue
            if (
                stress >= self.pressure_stress_threshold
                and goal.priority < self.pressure_blocks_below_priority
            ):
                if self.mark_blocked(goal.id, tick, "blocked under high stress"):
                    changed.append(goal)
        return changed

    def context(self, limit: int = 3) -> List[Dict[str, Any]]:
        goals = self.active_goals(limit=limit)
        if len(goals) < limit:
            blocked = [g for g in self._goals if g.status == GoalStatus.BLOCKED]
            blocked.sort(key=lambda g: (g.priority, -g.last_pursued_tick), reverse=True)
            goals.extend(blocked[: limit - len(goals)])
        return [
            {
                "id": goal.id,
                "description": goal.description,
                "priority": round(goal.priority, 3),
                "status": goal.status.value,
                "created_tick": goal.created_tick,
                "last_pursued_tick": goal.last_pursued_tick,
                "failure_count": goal.failure_count,
            }
            for goal in goals[:limit]
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "persistent",
            "config": {
                "max_active_goals": self.max_active_goals,
                "stale_after_ticks": self.stale_after_ticks,
                "block_after_failures": self.block_after_failures,
                "abandon_after_failures": self.abandon_after_failures,
                "pressure_stress_threshold": self.pressure_stress_threshold,
                "pressure_blocks_below_priority": self.pressure_blocks_below_priority,
            },
            "goals": [goal.to_dict() for goal in self._goals],
        }

    def restore(self, data: Any) -> None:
        if not data:
            self._goals = []
            return
        if isinstance(data, list):
            raw_goals = data
        elif isinstance(data, dict):
            self._restore_config(data.get("config"))
            raw_goals = data.get("goals", [])
        else:
            raw_goals = []
        restored: List[Goal] = []
        for item in raw_goals or []:
            if not isinstance(item, dict):
                continue
            goal = Goal.from_dict(item)
            if goal.id and goal.description:
                restored.append(goal)
        self._goals = restored

    def _restore_config(self, config: Any) -> None:
        if not isinstance(config, dict):
            return
        int_fields = (
            "max_active_goals",
            "stale_after_ticks",
            "block_after_failures",
            "abandon_after_failures",
        )
        float_fields = (
            "pressure_stress_threshold",
            "pressure_blocks_below_priority",
        )
        for name in int_fields:
            if name in config:
                try:
                    setattr(self, name, int(config[name]))
                except (TypeError, ValueError):
                    pass
        for name in float_fields:
            if name in config:
                try:
                    setattr(self, name, float(config[name]))
                except (TypeError, ValueError):
                    pass

    def _find(self, goal_id: str) -> Optional[Goal]:
        for goal in self._goals:
            if goal.id == goal_id:
                return goal
        return None

    @staticmethod
    def _append_note(goal: Goal, tick: int, label: str, text: str = "") -> None:
        suffix = f": {text}" if text else ""
        goal.notes.append(f"t{tick}:{label}{suffix}")
        if len(goal.notes) > 20:
            goal.notes = goal.notes[-20:]

    @staticmethod
    def _make_id(description: str, tick: int, source: str) -> str:
        seed = f"{tick}:{source}:{_normalize_description(description)}"
        return "goal_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


__all__ = ["PersistentGoalStack"]
