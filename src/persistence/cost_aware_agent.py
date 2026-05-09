"""Cost-aware wrapper around Agno's `Agent.run`.

Adds two side-effects to every agent call:
1. Token usage extraction from `RunOutput.metrics` → ICostTracker.
2. Optional fallback chain via Agno's `FallbackConfig` (handled by Agno
   itself; we only configure it).

Usage:
    invoker = AgnoModelInvoker(agent=my_agent, cost_tracker=tracker, agent_name="Perception")
    result = invoker.invoke("Hello", tick=42)

Or, if you don't want to wrap everything in InvocationResult, use
`record_run_metrics(response, tracker, agent_name)` to extract usage
directly from a fresh `agent.run()` response.

We rely on Agno >= 2.5 for `RunOutput.metrics` shape (see metrics.py
in libs/agno/agno).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

import structlog

from src.contracts.cost import (
    ICostTracker,
    IModelInvoker,
    InvocationResult,
    NullCostTracker,
    TokenUsage,
)

logger = structlog.get_logger("consciousness.persistence.cost_aware_agent")


def _extract_token_usage(response: Any, fallback_model_id: str) -> Optional[TokenUsage]:
    """Pull usage data out of an Agno RunOutput (or compatible).

    Handles the shape of Agno's RunMetrics:
        response.metrics.input_tokens / output_tokens / cached_read_tokens
                       / reasoning_tokens / cost / details (per-model)
    Older / mocked agents may not expose this — we degrade silently.
    """
    metrics = getattr(response, "metrics", None)
    if metrics is None:
        return None

    input_tokens = int(getattr(metrics, "input_tokens", 0) or 0)
    output_tokens = int(getattr(metrics, "output_tokens", 0) or 0)
    cached_tokens = int(
        getattr(metrics, "cache_read_tokens", 0)
        or getattr(metrics, "cached_tokens", 0)
        or 0
    )
    reasoning_tokens = int(getattr(metrics, "reasoning_tokens", 0) or 0)
    cost = float(getattr(metrics, "cost", 0.0) or 0.0)

    # Pick the best model id we can find
    model_id = fallback_model_id
    details = getattr(metrics, "details", None)
    if isinstance(details, dict) and details:
        # `details` is typically {model_id: ModelMetrics}; take the first key.
        try:
            model_id = next(iter(details.keys())) or model_id
        except StopIteration:
            pass

    if input_tokens == 0 and output_tokens == 0 and reasoning_tokens == 0:
        return None  # nothing meaningful to record

    return TokenUsage(
        model_id=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        reasoning_tokens=reasoning_tokens,
        cost_usd=cost,
    )


def record_run_metrics(
    response: Any,
    tracker: ICostTracker,
    agent_name: str,
    fallback_model_id: str,
    tick: int = 0,
) -> Optional[TokenUsage]:
    """Extract + record. Returns the TokenUsage that was recorded, or None."""
    usage = _extract_token_usage(response, fallback_model_id)
    if usage is None:
        return None
    try:
        tracker.record(usage, agent=agent_name, tick=tick)
    except Exception as e:
        logger.error("cost_record_failed", agent=agent_name, error=str(e))
    return usage


@dataclass
class AgnoModelInvoker:
    """`IModelInvoker` implementation backed by an Agno Agent.

    The agent already handles fallback (via its `fallback_config` /
    `fallback_models`). We just call .run() and harvest metrics.
    """

    agent: Any  # agno.agent.Agent
    cost_tracker: ICostTracker
    agent_name: str = "unknown"
    primary_model_id: str = "unknown"

    def invoke(
        self,
        prompt: str,
        agent_name: str = "unknown",
        tick: int = 0,
        **kwargs: Any,
    ) -> InvocationResult:
        try:
            response = self.agent.run(prompt, **kwargs)
        except Exception as e:
            logger.error(
                "model_invoke_error",
                agent=agent_name or self.agent_name,
                error=str(e),
            )
            return InvocationResult(
                success=False,
                error=str(e),
                model_used=self.primary_model_id,
            )

        usage = record_run_metrics(
            response,
            tracker=self.cost_tracker,
            agent_name=agent_name or self.agent_name,
            fallback_model_id=self.primary_model_id,
            tick=tick,
        )

        # Determine which model actually answered (Agno may have used a fallback).
        model_used = self.primary_model_id
        chain: List[str] = []
        try:
            details = getattr(response.metrics, "details", None)
            if isinstance(details, dict) and details:
                chain = list(details.keys())
                model_used = chain[-1] if chain else model_used
        except Exception:
            pass

        return InvocationResult(
            success=True,
            content=getattr(response, "content", None),
            usage=usage,
            model_used=model_used,
            fallback_chain=chain,
            raw=response,
        )


def build_fallback_config(
    fallback_model_ids: List[str],
) -> Optional[Any]:
    """Build an Agno FallbackConfig from a list of provider/model strings.

    Imports Agno lazily so this module remains useful in pure-test
    environments. Returns None on import error or empty list.
    """
    if not fallback_model_ids:
        return None
    try:
        from agno.models.fallback import FallbackConfig
        from agno.models.openrouter import OpenRouter
    except ImportError:
        logger.warning("agno_fallback_unavailable")
        return None

    fallback_models = [OpenRouter(id=mid) for mid in fallback_model_ids]
    return FallbackConfig(
        on_error=fallback_models,
        on_rate_limit=fallback_models,
        on_context_overflow=fallback_models,
    )


__all__ = [
    "AgnoModelInvoker",
    "build_fallback_config",
    "record_run_metrics",
]
