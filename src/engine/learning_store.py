"""Deterministic self-learning store.

This is the small, local equivalent of the Agno learning-store pattern. It
keeps the current session coherent and preserves reusable insights extracted
from reflection/planning outputs, while avoiding extra LLM calls.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.contracts.learning import LearnedInsight, SessionContext


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[\w\-]+", text.lower())
        if len(token) >= 3
    }


def _positive_int(value: Any, default: int) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return max(1, int(default))


def _non_negative_int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return max(0, int(default))


@dataclass
class PersistentLearningStore:
    """Checkpointable learning store with deterministic recall."""

    session_id: str = "default"
    max_recent_events: int = 12
    max_insights: int = 100
    min_insight_length: int = 12

    session_context: SessionContext = field(init=False)
    _insights: Dict[str, LearnedInsight] = field(default_factory=dict)
    _insight_order: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.max_recent_events = _positive_int(self.max_recent_events, 12)
        self.max_insights = _positive_int(self.max_insights, 100)
        self.min_insight_length = _positive_int(self.min_insight_length, 12)
        self.session_context = SessionContext(session_id=self.session_id)

    def record_interaction(
        self,
        tick: int,
        stimulus: str,
        result: Dict[str, Any],
        current_goal: Optional[Dict[str, Any]] = None,
    ) -> SessionContext:
        payload = result if isinstance(result, dict) else {}
        planning = payload.get("planning")
        planning = planning if isinstance(planning, dict) else {}

        response = str(payload.get("response") or planning.get("response") or "")
        intent = str(planning.get("intent") or "")
        next_actions = planning.get("next_actions") or []
        if not isinstance(next_actions, list):
            next_actions = []
        goal_progress = str(planning.get("goal_progress") or "")
        goal_reason = str(planning.get("goal_progress_reason") or "")

        ctx = self.session_context
        ctx.interaction_count += 1
        ctx.updated_tick = int(tick)
        ctx.last_intent = intent
        ctx.last_response = response[:500]
        ctx.current_plan = [str(action) for action in next_actions[:6]]
        if current_goal:
            ctx.current_goal = str(current_goal.get("description") or "")
        if goal_progress and goal_progress.lower() not in {"none", "n/a"}:
            ctx.progress = (
                f"{goal_progress}: {goal_reason}" if goal_reason else goal_progress
            )[:500]

        event = {
            "tick": int(tick),
            "stimulus": str(stimulus)[:240],
            "intent": intent[:160],
            "response": response[:240],
            "goal_progress": goal_progress,
        }
        ctx.recent_events.append(event)
        ctx.recent_events = ctx.recent_events[-self.max_recent_events :]
        ctx.summary = self._build_summary()
        return ctx

    def record_reflection(
        self,
        tick: int,
        reflection: Dict[str, Any],
    ) -> Optional[LearnedInsight]:
        payload = reflection if isinstance(reflection, dict) else {}
        insight_text = str(payload.get("insight") or "").strip()
        if len(insight_text) < self.min_insight_length:
            return None

        existing = self._find_duplicate(insight_text)
        if existing:
            existing.confidence = min(1.0, existing.confidence + 0.05)
            existing.last_used_tick = int(tick)
            return existing

        insight = LearnedInsight(
            id=uuid.uuid4().hex[:12],
            title=self._title_for(insight_text),
            learning=insight_text,
            context=str(payload.get("thought") or "")[:500],
            source=str(payload.get("_type") or "reflection"),
            created_tick=int(tick),
            last_used_tick=int(tick),
            confidence=0.65,
            tags=self._tags_for(insight_text),
        )
        self._insights[insight.id] = insight
        self._insight_order.append(insight.id)
        self._prune()
        return insight

    def recall(self, query: str, limit: int = 5) -> List[LearnedInsight]:
        limit_n = _non_negative_int(limit, 5)
        if limit_n == 0 or not self._insights:
            return []
        query_text = str(query or "")
        if not query_text:
            return [
                self._insights[insight_id]
                for insight_id in self._insight_order[-limit_n:]
                if insight_id in self._insights
            ][::-1]
        q_tokens = _tokenize(query_text)
        scored: List[tuple[float, LearnedInsight]] = []
        for insight in self._insights.values():
            text = f"{insight.title} {insight.learning} {insight.context}"
            i_tokens = _tokenize(text)
            overlap = len(q_tokens & i_tokens)
            if overlap == 0:
                continue
            score = overlap / max(1, len(q_tokens))
            score += 0.1 * float(insight.confidence)
            scored.append((score, insight))
        scored.sort(
            key=lambda item: (item[0], item[1].confidence, item[1].created_tick),
            reverse=True,
        )
        recalled = [insight for _, insight in scored[:limit_n]]
        for insight in recalled:
            insight.last_used_tick = max(
                insight.last_used_tick,
                self.session_context.updated_tick,
            )
        return recalled

    def context(self, query: str = "", limit: int = 3) -> Dict[str, Any]:
        return {
            "type": "persistent",
            "session_context": self.session_context.to_dict(),
            "insight_count": len(self._insights),
            "learned_insights": [
                insight.to_dict() for insight in self.recall(query, limit=limit)
            ],
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "persistent",
            "config": {
                "session_id": self.session_id,
                "max_recent_events": self.max_recent_events,
                "max_insights": self.max_insights,
                "min_insight_length": self.min_insight_length,
            },
            "session_context": self.session_context.to_dict(),
            "insight_count": len(self._insights),
            "learned_insights": [
                self._insights[insight_id].to_dict()
                for insight_id in self._insight_order
                if insight_id in self._insights
            ],
        }

    def restore(self, data: Any) -> None:
        if not isinstance(data, dict):
            return
        config = data.get("config") or {}
        if isinstance(config, dict):
            self.session_id = str(config.get("session_id") or self.session_id)
            self.max_recent_events = _positive_int(
                config.get("max_recent_events"),
                self.max_recent_events,
            )
            self.max_insights = _positive_int(
                config.get("max_insights"),
                self.max_insights,
            )
            self.min_insight_length = _positive_int(
                config.get("min_insight_length"),
                self.min_insight_length,
            )
        ctx_raw = data.get("session_context")
        if isinstance(ctx_raw, dict):
            self.session_context = SessionContext.from_dict(ctx_raw)
        insights = data.get("learned_insights")
        self._insights = {}
        self._insight_order = []
        if isinstance(insights, list):
            for item in insights:
                if not isinstance(item, dict):
                    continue
                insight = LearnedInsight.from_dict(item)
                if not insight.id or not insight.learning:
                    continue
                self._insights[insight.id] = insight
                self._insight_order.append(insight.id)
        self._prune()

    def _build_summary(self) -> str:
        events = self.session_context.recent_events[-3:]
        if not events:
            return ""
        parts = []
        for event in events:
            intent = event.get("intent") or "processed stimulus"
            response = event.get("response") or ""
            parts.append(f"t{event.get('tick')}: {intent} -> {response[:120]}")
        return " | ".join(parts)[:1000]

    def _find_duplicate(self, learning: str) -> Optional[LearnedInsight]:
        candidate_tokens = _tokenize(learning)
        for insight in self._insights.values():
            existing_tokens = _tokenize(insight.learning)
            if not candidate_tokens or not existing_tokens:
                continue
            overlap = len(candidate_tokens & existing_tokens)
            similarity = overlap / max(len(candidate_tokens), len(existing_tokens))
            if similarity >= 0.8:
                return insight
        return None

    @staticmethod
    def _title_for(learning: str) -> str:
        title = learning.strip().split(".")[0]
        return title[:80] or "learned insight"

    @staticmethod
    def _tags_for(learning: str) -> List[str]:
        tags = sorted(_tokenize(learning))
        return tags[:8]

    def _prune(self) -> None:
        while len(self._insight_order) > self.max_insights:
            old_id = self._insight_order.pop(0)
            self._insights.pop(old_id, None)


__all__ = ["PersistentLearningStore"]
