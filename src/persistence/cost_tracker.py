"""Cost tracker — token + USD accounting with daily budget cap.

Strategy:
- Each LLM call site records a TokenUsage event (see contracts.cost).
- The tracker aggregates per-model and per-agent counts, plus daily
  total spend.
- `is_budget_exceeded()` lets callers degrade gracefully (skip call,
  switch to a cheaper model, or just log).
- `reset_daily()` is intended to be called at midnight (or whenever the
  budget should reset) — we don't run a scheduler, the loop calls it.

Per-model pricing rates are configurable. Defaults are based on OpenRouter
public pricing (Nov 2025) for the models used by this project. Unknown
models default to a conservative high-side estimate so we never
under-bill ourselves into a runaway scenario.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict, Optional

import structlog

from src.contracts.cost import ICostTracker, TokenUsage

logger = structlog.get_logger("consciousness.persistence.cost")


@dataclass
class ModelRate:
    """Per-million-tokens USD rates for one model."""

    input_usd_per_mtok: float
    output_usd_per_mtok: float
    cached_usd_per_mtok: float = 0.0  # Anthropic prompt caching, OpenAI cache


# Default rates for models commonly used by the project.
# Values are public-listed rates — adjust if your contract differs.
DEFAULT_MODEL_RATES: Dict[str, ModelRate] = {
    # Grok 4.20 family (OpenRouter, Nov 2025 listing)
    "x-ai/grok-4.20": ModelRate(input_usd_per_mtok=3.0, output_usd_per_mtok=15.0),
    "xai/grok-4.20": ModelRate(input_usd_per_mtok=3.0, output_usd_per_mtok=15.0),

    # Claude Sonnet 4 family
    "anthropic/claude-sonnet-4-20250514": ModelRate(
        input_usd_per_mtok=3.0,
        output_usd_per_mtok=15.0,
        cached_usd_per_mtok=0.3,
    ),

    # Claude Opus 4.x family
    "anthropic/claude-opus-4-1": ModelRate(
        input_usd_per_mtok=15.0, output_usd_per_mtok=75.0, cached_usd_per_mtok=1.5
    ),

    # GPT-4o / GPT-4o-mini
    "openai/gpt-4o": ModelRate(input_usd_per_mtok=2.5, output_usd_per_mtok=10.0),
    "openai/gpt-4o-mini": ModelRate(input_usd_per_mtok=0.15, output_usd_per_mtok=0.6),
}

# Conservative fallback for unknown models — assume Sonnet-4 pricing.
UNKNOWN_MODEL_RATE = ModelRate(input_usd_per_mtok=3.0, output_usd_per_mtok=15.0)


@dataclass
class _ModelStats:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0
    call_count: int = 0


class InMemoryCostTracker:
    """ICostTracker backed by a Python dict + lock.

    Resets:
        Daily aggregations are reset by `reset_daily()` (typically called
        at midnight or whenever the tracker thinks the day rolled over).
        The current implementation is naive — no auto-rollover. The loop
        is responsible for calling reset_daily() explicitly.
    """

    def __init__(
        self,
        daily_budget_usd: float = 5.0,
        rates: Optional[Dict[str, ModelRate]] = None,
        alert_threshold_pct: float = 0.8,
    ) -> None:
        self._daily_budget_usd = daily_budget_usd
        self._rates: Dict[str, ModelRate] = dict(rates or DEFAULT_MODEL_RATES)
        self._alert_threshold_pct = alert_threshold_pct
        self._lock = Lock()

        # Aggregations
        self._daily_spent_usd: float = 0.0
        self._daily_started_at_ms: int = int(time.time() * 1000)
        self._per_model: Dict[str, _ModelStats] = {}
        self._per_agent: Dict[str, _ModelStats] = {}
        self._alerted = False

    def _get_rate(self, model_id: str) -> ModelRate:
        if model_id in self._rates:
            return self._rates[model_id]
        # Tolerant lookup: strip prefix
        for known_id, rate in self._rates.items():
            if known_id.endswith(model_id) or model_id.endswith(known_id):
                return rate
        return UNKNOWN_MODEL_RATE

    @staticmethod
    def estimate_cost(usage: TokenUsage, rate: ModelRate) -> float:
        """Compute USD cost from a usage event."""
        input_cost = (usage.input_tokens / 1_000_000.0) * rate.input_usd_per_mtok
        output_cost = (usage.output_tokens / 1_000_000.0) * rate.output_usd_per_mtok
        cached_cost = (usage.cached_tokens / 1_000_000.0) * rate.cached_usd_per_mtok
        # Reasoning tokens billed at output rate
        reasoning_cost = (usage.reasoning_tokens / 1_000_000.0) * rate.output_usd_per_mtok
        return input_cost + output_cost + cached_cost + reasoning_cost

    def record(self, usage: TokenUsage, agent: str = "unknown", tick: int = 0) -> None:
        rate = self._get_rate(usage.model_id)
        # Use the cost we got from the upstream provider if it's set, else estimate
        cost = usage.cost_usd if usage.cost_usd > 0 else self.estimate_cost(usage, rate)

        with self._lock:
            self._daily_spent_usd += cost

            mstats = self._per_model.setdefault(usage.model_id, _ModelStats())
            mstats.input_tokens += usage.input_tokens
            mstats.output_tokens += usage.output_tokens
            mstats.cached_tokens += usage.cached_tokens
            mstats.reasoning_tokens += usage.reasoning_tokens
            mstats.cost_usd += cost
            mstats.call_count += 1

            astats = self._per_agent.setdefault(agent, _ModelStats())
            astats.input_tokens += usage.input_tokens
            astats.output_tokens += usage.output_tokens
            astats.cached_tokens += usage.cached_tokens
            astats.reasoning_tokens += usage.reasoning_tokens
            astats.cost_usd += cost
            astats.call_count += 1

            should_alert = (
                not self._alerted
                and self._daily_budget_usd > 0
                and self._daily_spent_usd >= self._daily_budget_usd * self._alert_threshold_pct
            )
            if should_alert:
                logger.warning(
                    "cost_alert_threshold",
                    spent_usd=round(self._daily_spent_usd, 4),
                    budget_usd=self._daily_budget_usd,
                    threshold_pct=self._alert_threshold_pct,
                )
                self._alerted = True

    def daily_spent_usd(self) -> float:
        return self._daily_spent_usd

    def daily_budget_usd(self) -> float:
        return self._daily_budget_usd

    def is_budget_exceeded(self) -> bool:
        return (
            self._daily_budget_usd > 0
            and self._daily_spent_usd >= self._daily_budget_usd
        )

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "type": "in_memory",
                "daily_spent_usd": round(self._daily_spent_usd, 4),
                "daily_budget_usd": self._daily_budget_usd,
                "remaining_usd": round(
                    max(0.0, self._daily_budget_usd - self._daily_spent_usd), 4
                ),
                "is_exceeded": self.is_budget_exceeded(),
                "alerted": self._alerted,
                "per_model": {
                    m: {
                        "input_tokens": s.input_tokens,
                        "output_tokens": s.output_tokens,
                        "cached_tokens": s.cached_tokens,
                        "reasoning_tokens": s.reasoning_tokens,
                        "cost_usd": round(s.cost_usd, 4),
                        "call_count": s.call_count,
                    }
                    for m, s in self._per_model.items()
                },
                "per_agent": {
                    a: {
                        "input_tokens": s.input_tokens,
                        "output_tokens": s.output_tokens,
                        "cached_tokens": s.cached_tokens,
                        "reasoning_tokens": s.reasoning_tokens,
                        "cost_usd": round(s.cost_usd, 4),
                        "call_count": s.call_count,
                    }
                    for a, s in self._per_agent.items()
                },
            }

    def reset_daily(self) -> None:
        with self._lock:
            self._daily_spent_usd = 0.0
            self._daily_started_at_ms = int(time.time() * 1000)
            self._per_model.clear()
            self._per_agent.clear()
            self._alerted = False
        logger.info("cost_tracker_reset_daily")


__all__ = [
    "DEFAULT_MODEL_RATES",
    "InMemoryCostTracker",
    "ModelRate",
    "UNKNOWN_MODEL_RATE",
]
