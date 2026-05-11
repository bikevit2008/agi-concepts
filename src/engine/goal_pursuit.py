"""Deterministic goal-pursuit policy.

Stage 29 made goals persistent. This policy makes them operational: when the
loop is idle and a goal has not received recent progress, it emits a bounded
internal stimulus that asks the normal Perception->Emotion->Memory->Planning
pipeline to take the next small step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from src.contracts.goals import Goal, GoalPursuitDecision, GoalStatus


@dataclass
class DeterministicGoalPursuitPolicy:
    """Rate-limited deterministic scheduler for active goal pursuit."""

    min_idle_ticks: int = 2
    min_ticks_between_attempts: int = 6
    progress_stale_after_ticks: int = 8
    max_attempts_per_goal: int = 20
    pause_stress_threshold: float = 0.92
    pause_low_priority_below: float = 0.5

    _last_attempt_tick_by_goal: Dict[str, int] = field(default_factory=dict)
    _attempts_by_goal: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._normalize_config()

    def maybe_pursue(
        self,
        tick: int,
        idle_ticks: int,
        goal: Optional[Goal],
        runtime_state: Dict[str, Any],
        hysteresis_state: Dict[str, float],
    ) -> Optional[GoalPursuitDecision]:
        if goal is None or goal.status != GoalStatus.ACTIVE:
            return None
        if idle_ticks < self.min_idle_ticks:
            return None
        if tick - goal.last_pursued_tick < self.progress_stale_after_ticks:
            return None

        last_attempt_tick = self._last_attempt_tick_by_goal.get(goal.id, -10**9)
        if tick - last_attempt_tick < self.min_ticks_between_attempts:
            return None

        attempts = self._attempts_by_goal.get(goal.id, 0)
        if attempts >= self.max_attempts_per_goal:
            return None

        stress = self._coerce_float(hysteresis_state.get("stress", 0.0), 0.0)
        if stress >= self.pause_stress_threshold and goal.priority < self.pause_low_priority_below:
            return None

        stimulus = self._build_stimulus(goal, attempts + 1)
        return GoalPursuitDecision(
            goal_id=goal.id,
            stimulus=stimulus,
            tick=tick,
            reason="idle_goal_pursuit",
        )

    def record(self, decision: GoalPursuitDecision) -> None:
        self._last_attempt_tick_by_goal[decision.goal_id] = decision.tick
        self._attempts_by_goal[decision.goal_id] = (
            self._attempts_by_goal.get(decision.goal_id, 0) + 1
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "deterministic",
            "config": {
                "min_idle_ticks": self.min_idle_ticks,
                "min_ticks_between_attempts": self.min_ticks_between_attempts,
                "progress_stale_after_ticks": self.progress_stale_after_ticks,
                "max_attempts_per_goal": self.max_attempts_per_goal,
                "pause_stress_threshold": self.pause_stress_threshold,
                "pause_low_priority_below": self.pause_low_priority_below,
            },
            "last_attempt_tick_by_goal": dict(self._last_attempt_tick_by_goal),
            "attempts_by_goal": dict(self._attempts_by_goal),
        }

    def restore(self, data: Any) -> None:
        if not isinstance(data, dict):
            return
        self._restore_config(data.get("config"))
        self._last_attempt_tick_by_goal = self._int_dict(
            data.get("last_attempt_tick_by_goal")
        )
        self._attempts_by_goal = self._int_dict(data.get("attempts_by_goal"))

    def _restore_config(self, config: Any) -> None:
        if not isinstance(config, dict):
            return
        int_fields = (
            "min_idle_ticks",
            "min_ticks_between_attempts",
            "progress_stale_after_ticks",
            "max_attempts_per_goal",
        )
        float_fields = ("pause_stress_threshold", "pause_low_priority_below")
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
        self._normalize_config()

    def _normalize_config(self) -> None:
        self.min_idle_ticks = max(0, self._coerce_int(self.min_idle_ticks, 2))
        self.min_ticks_between_attempts = max(
            1,
            self._coerce_int(self.min_ticks_between_attempts, 6),
        )
        self.progress_stale_after_ticks = max(
            0,
            self._coerce_int(self.progress_stale_after_ticks, 8),
        )
        self.max_attempts_per_goal = max(
            0,
            self._coerce_int(self.max_attempts_per_goal, 20),
        )
        self.pause_stress_threshold = min(
            1.0,
            max(0.0, self._coerce_float(self.pause_stress_threshold, 0.92)),
        )
        self.pause_low_priority_below = min(
            1.0,
            max(0.0, self._coerce_float(self.pause_low_priority_below, 0.5)),
        )

    @staticmethod
    def _coerce_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _int_dict(raw: Any) -> Dict[str, int]:
        if not isinstance(raw, dict):
            return {}
        converted: Dict[str, int] = {}
        for key, value in raw.items():
            try:
                converted[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
        return converted

    @staticmethod
    def _build_stimulus(goal: Goal, attempt: int) -> str:
        return (
            f"[goal:{goal.id}] Continue the durable goal: {goal.description}. "
            f"Attempt {attempt}. Formulate the next small step, check current "
            "body/resource constraints, and stay aligned with the goal."
        )


__all__ = ["DeterministicGoalPursuitPolicy"]
