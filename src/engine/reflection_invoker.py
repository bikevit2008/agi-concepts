"""Adapter that turns an Agno reflection agent into a `ReflectionInvoker`.

Provides:
    build_agno_reflection_invoker(agent, cost_tracker, primary_model_id)
        → callable(prompt, members) -> ReflectionAbstraction | None

The invoker:
  - calls agent.run(prompt)
  - records token usage in the cost tracker
  - returns the structured response (Agno's output_schema parsing)
  - swallows exceptions and returns None on failure (doesn't poison
    the consolidation cycle)
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional

import structlog

from src.contracts.cost import ICostTracker
from src.contracts.memory import MemoryEntry
from src.persistence.cost_aware_agent import record_run_metrics

logger = structlog.get_logger("consciousness.engine.reflection_invoker")


def build_agno_reflection_invoker(
    agent: Any,
    cost_tracker: ICostTracker,
    primary_model_id: str,
    agent_name: str = "ReflectionConsolidator",
) -> Callable[[str, List[MemoryEntry]], Optional[Any]]:
    """Returns a `ReflectionInvoker` (signature: prompt, members → object).

    The returned object is whatever the agent's output_schema produced
    (typically `ReflectionAbstraction`). On any failure it returns None.
    """

    def _invoke(prompt: str, members: List[MemoryEntry]) -> Optional[Any]:
        try:
            response = agent.run(prompt)
        except Exception as e:
            logger.warning("reflection_agent_run_failed", error=str(e))
            return None
        try:
            record_run_metrics(
                response,
                tracker=cost_tracker,
                agent_name=agent_name,
                fallback_model_id=primary_model_id,
                tick=0,
            )
        except Exception:
            pass
        content = getattr(response, "content", None)
        if content is None:
            return None
        # Agno may already return the parsed Pydantic model; if it returns
        # a string, the consolidator falls back since `getattr` won't find
        # the attributes we need.
        return content

    return _invoke


__all__ = ["build_agno_reflection_invoker"]
