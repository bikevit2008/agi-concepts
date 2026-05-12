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

from src.contracts.learning import LearnedInsight, LearningMode, SessionContext


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[\w\-]+", text.lower())
        if len(token) >= 3
    }


def _normalize_learning(text: str) -> str:
    normalized = re.sub(r"[^\w\s\-]", "", str(text).lower())
    return re.sub(r"\s+", " ", normalized).strip()


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


def _bounded_float(
    value: Any,
    default: float,
    min_value: float = 0.0,
    max_value: float = 1.0,
) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = float(default)
    return min(max_value, max(min_value, parsed))


@dataclass
class PersistentLearningStore:
    """Checkpointable learning store with deterministic recall."""

    session_id: str = "default"
    mode: str = LearningMode.ALWAYS.value
    max_recent_events: int = 12
    max_insights: int = 100
    min_insight_length: int = 12
    curation_interval_ticks: int = 25
    stale_after_ticks: int = 500
    stale_confidence_decay: float = 0.05

    session_context: SessionContext = field(init=False)
    _insights: Dict[str, LearnedInsight] = field(default_factory=dict)
    _insight_order: List[str] = field(default_factory=list)
    _proposals: Dict[str, LearnedInsight] = field(default_factory=dict)
    _proposal_order: List[str] = field(default_factory=list)
    _curation_runs: int = 0
    _last_curated_tick: int = 0
    _last_curation: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.mode = LearningMode.normalize(self.mode).value
        self.max_recent_events = _positive_int(self.max_recent_events, 12)
        self.max_insights = _positive_int(self.max_insights, 100)
        self.min_insight_length = _positive_int(self.min_insight_length, 12)
        self.curation_interval_ticks = _non_negative_int(
            self.curation_interval_ticks,
            25,
        )
        self.stale_after_ticks = _non_negative_int(self.stale_after_ticks, 500)
        self.stale_confidence_decay = _bounded_float(
            self.stale_confidence_decay,
            0.05,
            min_value=0.0,
            max_value=1.0,
        )
        self.session_context = SessionContext(session_id=self.session_id)

    def record_interaction(
        self,
        tick: int,
        stimulus: str,
        result: Dict[str, Any],
        current_goal: Optional[Dict[str, Any]] = None,
    ) -> SessionContext:
        if self.mode == LearningMode.DISABLED.value:
            return self.session_context
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
        if self.mode == LearningMode.DISABLED.value:
            return None
        payload = reflection if isinstance(reflection, dict) else {}
        insight_text = str(payload.get("insight") or "").strip()
        if len(insight_text) < self.min_insight_length:
            return None

        if self.mode == LearningMode.PROPOSE.value:
            self._propose_insight(tick=int(tick), payload=payload)
            return None
        if (
            self.mode == LearningMode.AGENTIC.value
            and not self._agentic_save_requested(payload)
        ):
            self._propose_insight(tick=int(tick), payload=payload)
            return None

        return self._save_insight(
            learning=insight_text,
            tick=int(tick),
            context=str(payload.get("thought") or "")[:500],
            source=str(payload.get("_type") or "reflection"),
            metadata={"mode": self.mode},
        )

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
            "mode": self.mode,
            "mode_guidance": self._mode_guidance(),
            "session_context": self.session_context.to_dict(),
            "insight_count": len(self._insights),
            "learned_insights": [
                insight.to_dict() for insight in self.recall(query, limit=limit)
            ],
            "proposal_count": len(self._proposals),
            "proposed_insights": [
                proposal.to_dict() for proposal in self.proposals(limit=limit)
            ],
        }

    def proposals(self, limit: int = 10) -> List[LearnedInsight]:
        limit_n = _non_negative_int(limit, 10)
        if limit_n == 0:
            return []
        return [
            self._proposals[proposal_id]
            for proposal_id in self._proposal_order[-limit_n:]
            if proposal_id in self._proposals
        ][::-1]

    def approve_proposal(
        self,
        proposal_id: str,
        tick: int = 0,
    ) -> Optional[LearnedInsight]:
        proposal = self._proposals.pop(str(proposal_id), None)
        if proposal is None:
            return None
        self._proposal_order = [
            item for item in self._proposal_order if item != proposal.id
        ]
        saved = self._save_insight(
            learning=proposal.learning,
            tick=int(tick or proposal.created_tick),
            context=proposal.context,
            source="approved_proposal",
            metadata={
                **proposal.metadata,
                "approved_tick": int(tick or proposal.created_tick),
                "proposal_id": proposal.id,
            },
        )
        return saved

    def reject_proposal(self, proposal_id: str) -> bool:
        proposal_id = str(proposal_id)
        existed = self._proposals.pop(proposal_id, None) is not None
        if existed:
            self._proposal_order = [
                item for item in self._proposal_order if item != proposal_id
            ]
        return existed

    def curate(self, tick: int = 0) -> Dict[str, Any]:
        tick_n = _non_negative_int(tick, self.session_context.updated_tick)
        before = len(self._insights)
        proposal_before = len(self._proposals)

        merged = self._merge_duplicate_insights()
        proposals_removed = self._curate_proposals()
        decayed, stale_pruned = self._decay_and_prune_stale(tick_n)
        capacity_pruned = self._prune()
        proposal_capacity_pruned = self._prune_proposals()
        removed = before - len(self._insights)

        self._curation_runs += 1
        self._last_curated_tick = tick_n
        self._last_curation = {
            "type": "persistent",
            "mode": self.mode,
            "tick": tick_n,
            "before": before,
            "after": len(self._insights),
            "removed": removed,
            "merged": merged,
            "decayed": decayed,
            "stale_pruned": stale_pruned,
            "capacity_pruned": capacity_pruned,
            "proposal_before": proposal_before,
            "proposal_after": len(self._proposals),
            "proposals_removed": proposals_removed + proposal_capacity_pruned,
        }
        return dict(self._last_curation)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "persistent",
            "mode": self.mode,
            "config": {
                "session_id": self.session_id,
                "mode": self.mode,
                "max_recent_events": self.max_recent_events,
                "max_insights": self.max_insights,
                "min_insight_length": self.min_insight_length,
                "curation_interval_ticks": self.curation_interval_ticks,
                "stale_after_ticks": self.stale_after_ticks,
                "stale_confidence_decay": self.stale_confidence_decay,
            },
            "session_context": self.session_context.to_dict(),
            "insight_count": len(self._insights),
            "learned_insights": [
                self._insights[insight_id].to_dict()
                for insight_id in self._insight_order
                if insight_id in self._insights
            ],
            "proposal_count": len(self._proposals),
            "proposed_insights": [
                self._proposals[proposal_id].to_dict()
                for proposal_id in self._proposal_order
                if proposal_id in self._proposals
            ],
            "curation": {
                "runs": self._curation_runs,
                "last_tick": self._last_curated_tick,
                "last": dict(self._last_curation),
            },
        }

    def restore(self, data: Any) -> None:
        if not isinstance(data, dict):
            return
        config = data.get("config") or {}
        if isinstance(config, dict):
            self.session_id = str(config.get("session_id") or self.session_id)
            self.mode = LearningMode.normalize(config.get("mode", self.mode)).value
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
            self.curation_interval_ticks = _non_negative_int(
                config.get("curation_interval_ticks"),
                self.curation_interval_ticks,
            )
            self.stale_after_ticks = _non_negative_int(
                config.get("stale_after_ticks"),
                self.stale_after_ticks,
            )
            self.stale_confidence_decay = _bounded_float(
                config.get("stale_confidence_decay"),
                self.stale_confidence_decay,
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
        proposals = data.get("proposed_insights")
        self._proposals = {}
        self._proposal_order = []
        if isinstance(proposals, list):
            for item in proposals:
                if not isinstance(item, dict):
                    continue
                proposal = LearnedInsight.from_dict(item)
                if not proposal.id or not proposal.learning:
                    continue
                self._proposals[proposal.id] = proposal
                self._proposal_order.append(proposal.id)
        self._prune_proposals()
        curation = data.get("curation")
        if isinstance(curation, dict):
            self._curation_runs = _non_negative_int(curation.get("runs"), 0)
            self._last_curated_tick = _non_negative_int(
                curation.get("last_tick"),
                0,
            )
            last = curation.get("last")
            self._last_curation = dict(last) if isinstance(last, dict) else {}

    def _save_insight(
        self,
        learning: str,
        tick: int,
        context: str = "",
        source: str = "reflection",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LearnedInsight:
        existing = self._find_duplicate(learning)
        if existing:
            existing.confidence = min(1.0, existing.confidence + 0.05)
            existing.last_used_tick = max(existing.last_used_tick, int(tick))
            existing.metadata.update(metadata or {})
            self._drop_matching_proposals(learning)
            return existing

        insight = LearnedInsight(
            id=uuid.uuid4().hex[:12],
            title=self._title_for(learning),
            learning=learning,
            context=context[:500],
            source=source,
            created_tick=int(tick),
            last_used_tick=int(tick),
            confidence=0.65,
            tags=self._tags_for(learning),
            metadata=dict(metadata or {}),
        )
        self._insights[insight.id] = insight
        self._insight_order.append(insight.id)
        self._drop_matching_proposals(learning)
        self._prune()
        return insight

    def _propose_insight(
        self,
        tick: int,
        payload: Dict[str, Any],
    ) -> Optional[LearnedInsight]:
        learning = str(payload.get("insight") or "").strip()
        if not learning:
            return None
        if self._find_duplicate(learning) is not None:
            return None
        existing = self._find_duplicate_proposal(learning)
        if existing:
            existing.confidence = min(1.0, existing.confidence + 0.03)
            existing.last_used_tick = max(existing.last_used_tick, int(tick))
            return existing

        proposal = LearnedInsight(
            id=uuid.uuid4().hex[:12],
            title=self._title_for(learning),
            learning=learning,
            context=str(payload.get("thought") or "")[:500],
            source="proposal",
            created_tick=int(tick),
            last_used_tick=int(tick),
            confidence=0.55,
            tags=self._tags_for(learning),
            metadata={
                "mode": self.mode,
                "original_source": str(payload.get("_type") or "reflection"),
                "status": "proposed",
            },
        )
        self._proposals[proposal.id] = proposal
        self._proposal_order.append(proposal.id)
        self._prune_proposals()
        return proposal

    @staticmethod
    def _agentic_save_requested(payload: Dict[str, Any]) -> bool:
        if payload.get("save_learning") is True:
            return True
        if payload.get("learn") is True or payload.get("should_learn") is True:
            return True
        action = str(payload.get("learning_action") or "").strip().lower()
        return action in {"save", "store", "remember"}

    def _mode_guidance(self) -> str:
        if self.mode == LearningMode.PROPOSE.value:
            return (
                "Use recalled insights as fallible prior experience; new insights "
                "are proposals until explicitly approved."
            )
        if self.mode == LearningMode.AGENTIC.value:
            return (
                "Use recalled insights as fallible prior experience; save new "
                "insights only when the agent explicitly requests learning."
            )
        if self.mode == LearningMode.DISABLED.value:
            return "Learning capture is disabled for this store."
        return (
            "Use recalled insights as fallible prior experience; durable "
            "reflection insights are captured automatically."
        )

    def _find_duplicate_proposal(self, learning: str) -> Optional[LearnedInsight]:
        for proposal in self._proposals.values():
            if self._are_duplicates(learning, proposal.learning):
                return proposal
        return None

    def _drop_matching_proposals(self, learning: str) -> int:
        removed = 0
        for proposal_id in list(self._proposal_order):
            proposal = self._proposals.get(proposal_id)
            if proposal is None:
                self._proposal_order.remove(proposal_id)
                continue
            if self._are_duplicates(learning, proposal.learning):
                self._proposals.pop(proposal_id, None)
                self._proposal_order.remove(proposal_id)
                removed += 1
        return removed

    def _merge_duplicate_insights(self) -> int:
        merged = 0
        kept_ids: List[str] = []
        for insight_id in list(self._insight_order):
            insight = self._insights.get(insight_id)
            if insight is None:
                continue
            duplicate = next(
                (
                    self._insights[kept_id]
                    for kept_id in kept_ids
                    if kept_id in self._insights
                    and self._are_duplicates(
                        self._insights[kept_id].learning,
                        insight.learning,
                    )
                ),
                None,
            )
            if duplicate is None:
                kept_ids.append(insight_id)
                continue
            self._merge_into(duplicate, insight, boost=True)
            self._insights.pop(insight_id, None)
            merged += 1
        self._insight_order = [
            insight_id for insight_id in kept_ids if insight_id in self._insights
        ]
        return merged

    def _curate_proposals(self) -> int:
        removed = 0
        kept_ids: List[str] = []
        for proposal_id in list(self._proposal_order):
            proposal = self._proposals.get(proposal_id)
            if proposal is None:
                continue
            if self._find_duplicate(proposal.learning) is not None:
                self._proposals.pop(proposal_id, None)
                removed += 1
                continue
            duplicate = next(
                (
                    self._proposals[kept_id]
                    for kept_id in kept_ids
                    if kept_id in self._proposals
                    and self._are_duplicates(
                        self._proposals[kept_id].learning,
                        proposal.learning,
                    )
                ),
                None,
            )
            if duplicate is None:
                kept_ids.append(proposal_id)
                continue
            self._merge_into(duplicate, proposal, boost=False)
            self._proposals.pop(proposal_id, None)
            removed += 1
        self._proposal_order = [
            proposal_id for proposal_id in kept_ids if proposal_id in self._proposals
        ]
        return removed

    def _decay_and_prune_stale(self, tick: int) -> tuple[int, int]:
        if self.stale_after_ticks <= 0 or tick <= 0:
            return (0, 0)
        decayed = 0
        pruned = 0
        for insight_id in list(self._insight_order):
            insight = self._insights.get(insight_id)
            if insight is None:
                continue
            last_active = max(insight.last_used_tick, insight.created_tick)
            if tick - last_active < self.stale_after_ticks:
                continue
            old_confidence = insight.confidence
            insight.confidence = max(0.0, insight.confidence - self.stale_confidence_decay)
            insight.metadata["last_curated_tick"] = tick
            if insight.confidence < old_confidence:
                decayed += 1
            if insight.confidence <= 0.2:
                self._insights.pop(insight_id, None)
                self._insight_order.remove(insight_id)
                pruned += 1
        return (decayed, pruned)

    @staticmethod
    def _merge_into(
        target: LearnedInsight,
        duplicate: LearnedInsight,
        boost: bool,
    ) -> None:
        target.created_tick = min(target.created_tick, duplicate.created_tick)
        target.last_used_tick = max(target.last_used_tick, duplicate.last_used_tick)
        if boost:
            target.confidence = min(
                1.0,
                max(target.confidence, duplicate.confidence) + 0.05,
            )
        else:
            target.confidence = max(target.confidence, duplicate.confidence)
        target.tags = sorted(set(target.tags) | set(duplicate.tags))[:12]
        if len(duplicate.context) > len(target.context):
            target.context = duplicate.context[:500]
        merged_ids = list(target.metadata.get("merged_ids") or [])
        merged_ids.append(duplicate.id)
        target.metadata["merged_ids"] = merged_ids[-20:]
        target.metadata.update(
            {
                key: value
                for key, value in duplicate.metadata.items()
                if key not in target.metadata
            }
        )

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
        for insight in self._insights.values():
            if self._are_duplicates(learning, insight.learning):
                return insight
        return None

    @staticmethod
    def _are_duplicates(left: str, right: str) -> bool:
        left_normalized = _normalize_learning(left)
        right_normalized = _normalize_learning(right)
        if not left_normalized or not right_normalized:
            return False
        if left_normalized == right_normalized:
            return True
        left_tokens = _tokenize(left_normalized)
        right_tokens = _tokenize(right_normalized)
        if not left_tokens or not right_tokens:
            return False
        overlap = len(left_tokens & right_tokens)
        similarity = overlap / max(len(left_tokens), len(right_tokens))
        return similarity >= 0.8

    @staticmethod
    def _title_for(learning: str) -> str:
        title = learning.strip().split(".")[0]
        return title[:80] or "learned insight"

    @staticmethod
    def _tags_for(learning: str) -> List[str]:
        tags = sorted(_tokenize(learning))
        return tags[:8]

    def _prune(self) -> int:
        removed = 0
        while len(self._insight_order) > self.max_insights:
            old_id = self._insight_order.pop(0)
            self._insights.pop(old_id, None)
            removed += 1
        return removed

    def _prune_proposals(self) -> int:
        removed = 0
        while len(self._proposal_order) > self.max_insights:
            old_id = self._proposal_order.pop(0)
            self._proposals.pop(old_id, None)
            removed += 1
        return removed


__all__ = ["PersistentLearningStore"]
