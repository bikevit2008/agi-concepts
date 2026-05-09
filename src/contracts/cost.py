"""Cost & model invocation contracts — token tracking + fallback chain.

Two distinct responsibilities:
1. ICostTracker — counts tokens & USD spend, enforces daily budget cap.
   Used as a side-channel collector; LLM call sites push usage events.
2. IModelInvoker — abstraction over Agno's Agent.run() that adds:
     * automatic fallback chain on rate-limit / context-overflow / errors
     * cost tracking integration (delegates to ICostTracker)
     * structured failure handling (returns invocation result with
       success/error fields rather than raising)

We use Agno's built-in FallbackConfig under the hood when possible;
the contract layer is here so the rest of the system is decoupled from
Agno-specific types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class TokenUsage:
    """Token counts + cost estimate for a single LLM call."""

    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0  # estimated based on per-model rates

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.reasoning_tokens


class CostBudgetExceeded(Exception):
    """Raised when daily cost cap is hit and a strict-budget call is attempted.

    Most call sites should treat this as a soft signal (log + degrade)
    rather than crashing the loop.
    """

    def __init__(self, daily_spent: float, daily_budget: float):
        super().__init__(f"Daily budget exceeded: ${daily_spent:.4f} / ${daily_budget:.4f}")
        self.daily_spent = daily_spent
        self.daily_budget = daily_budget


@runtime_checkable
class ICostTracker(Protocol):
    """Tracks token usage and USD cost across the system."""

    def record(self, usage: TokenUsage, agent: str = "unknown", tick: int = 0) -> None:
        """Record a usage event."""
        ...

    def daily_spent_usd(self) -> float:
        """Total USD spent today (rolling 24h window from process start)."""
        ...

    def daily_budget_usd(self) -> float:
        """Configured daily cap."""
        ...

    def is_budget_exceeded(self) -> bool:
        """Check if daily spend has exceeded the cap."""
        ...

    def stats(self) -> Dict[str, Any]:
        """Aggregated stats for observability/UI."""
        ...

    def reset_daily(self) -> None:
        """Reset daily counters (typically scheduled at midnight)."""
        ...


@dataclass
class InvocationResult:
    """Result of an LLM invocation, success or failure.

    Decoupled from Agno's RunOutput so we can swap providers later.
    """

    success: bool
    content: Any = None
    usage: Optional[TokenUsage] = None
    model_used: Optional[str] = None
    fallback_chain: List[str] = field(default_factory=list)  # models tried
    error: Optional[str] = None
    raw: Any = None  # original RunOutput from Agno, for advanced consumers


@runtime_checkable
class IModelInvoker(Protocol):
    """Wraps an Agno Agent (or similar) with cost tracking + fallback chain.

    Concrete implementation is AgnoModelInvoker; tests can inject mocks.
    """

    def invoke(
        self,
        prompt: str,
        agent_name: str = "unknown",
        tick: int = 0,
        **kwargs: Any,
    ) -> InvocationResult:
        """Run the underlying agent; record usage; apply fallback if needed."""
        ...


# ---------------------------------------------------------------------------
# Null implementations (Null Object Pattern)
# ---------------------------------------------------------------------------


class NullCostTracker:
    """No-op cost tracker: records nothing, never trips budget."""

    def record(self, usage: TokenUsage, agent: str = "unknown", tick: int = 0) -> None:
        return None

    def daily_spent_usd(self) -> float:
        return 0.0

    def daily_budget_usd(self) -> float:
        return float("inf")

    def is_budget_exceeded(self) -> bool:
        return False

    def stats(self) -> Dict[str, Any]:
        return {"type": "null", "daily_spent_usd": 0.0}

    def reset_daily(self) -> None:
        return None
