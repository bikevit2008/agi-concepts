"""Helper for building Agno fallback chains for our agents.

Each agent factory calls `build_fallback_models(model_settings)` to get
a list of OpenRouter models that Agno will try when the primary model
fails (rate-limit / context-overflow / generic provider error).

Reads from `model_settings.fallback_models`, which is a list of
provider/id strings like:
    - "anthropic/claude-sonnet-4-20250514"
    - "openai/gpt-4o"
"""

from __future__ import annotations

from typing import Any, List

from src.config.settings import ModelSettings


def build_fallback_models(model_settings: ModelSettings) -> List[Any]:
    """Return [OpenRouter(id=…), …] for each fallback in settings.

    Empty list if no fallbacks configured. Callers can pass this directly
    to `Agent(fallback_models=...)`.
    """
    if not model_settings.fallback_models:
        return []
    try:
        from agno.models.openrouter import OpenRouter
    except ImportError:
        return []
    return [OpenRouter(id=mid) for mid in model_settings.fallback_models]


__all__ = ["build_fallback_models"]
