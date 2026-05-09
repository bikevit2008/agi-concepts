"""Tests for InMemoryCostTracker (Stage 6) + record_run_metrics helper."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.contracts.cost import ICostTracker, NullCostTracker, TokenUsage
from src.persistence.cost_aware_agent import (
    AgnoModelInvoker,
    record_run_metrics,
)
from src.persistence.cost_tracker import (
    DEFAULT_MODEL_RATES,
    InMemoryCostTracker,
    ModelRate,
    UNKNOWN_MODEL_RATE,
)


# --- Cost tracking ---------------------------------------------------------


def test_record_increments_daily_spent():
    t = InMemoryCostTracker(daily_budget_usd=100.0)
    assert t.daily_spent_usd() == 0.0
    t.record(
        TokenUsage(model_id="x-ai/grok-4.20", input_tokens=1_000_000, output_tokens=0),
        agent="Test",
    )
    # 1M input tokens at $3 → exactly $3.00
    assert abs(t.daily_spent_usd() - 3.0) < 1e-6


def test_record_uses_provided_cost_when_set():
    t = InMemoryCostTracker(daily_budget_usd=100.0)
    t.record(
        TokenUsage(
            model_id="x-ai/grok-4.20",
            input_tokens=1_000_000,
            output_tokens=0,
            cost_usd=42.0,  # provider-supplied — must override estimate
        ),
        agent="Test",
    )
    assert t.daily_spent_usd() == pytest.approx(42.0)


def test_unknown_model_uses_fallback_rate():
    t = InMemoryCostTracker(daily_budget_usd=100.0)
    t.record(
        TokenUsage(
            model_id="totally-unknown/foo",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        ),
        agent="Test",
    )
    expected = (
        1.0 * UNKNOWN_MODEL_RATE.input_usd_per_mtok
        + 1.0 * UNKNOWN_MODEL_RATE.output_usd_per_mtok
    )
    assert abs(t.daily_spent_usd() - expected) < 1e-6


def test_is_budget_exceeded():
    t = InMemoryCostTracker(daily_budget_usd=0.05)
    assert not t.is_budget_exceeded()
    t.record(
        TokenUsage(model_id="openai/gpt-4o-mini", input_tokens=1_000_000, output_tokens=1_000_000),
        agent="Test",
    )
    # 1M input * $0.15 + 1M output * $0.60 = $0.75 → over $0.05
    assert t.is_budget_exceeded()


def test_per_agent_aggregation():
    t = InMemoryCostTracker()
    t.record(
        TokenUsage(model_id="x-ai/grok-4.20", input_tokens=100, output_tokens=200),
        agent="Perception",
    )
    t.record(
        TokenUsage(model_id="x-ai/grok-4.20", input_tokens=300, output_tokens=400),
        agent="Emotion",
    )
    stats = t.stats()
    assert stats["per_agent"]["Perception"]["input_tokens"] == 100
    assert stats["per_agent"]["Perception"]["output_tokens"] == 200
    assert stats["per_agent"]["Emotion"]["input_tokens"] == 300
    assert stats["per_agent"]["Emotion"]["output_tokens"] == 400


def test_per_model_aggregation():
    t = InMemoryCostTracker()
    t.record(
        TokenUsage(model_id="x-ai/grok-4.20", input_tokens=100, output_tokens=200),
        agent="A",
    )
    t.record(
        TokenUsage(model_id="anthropic/claude-sonnet-4-20250514", input_tokens=50, output_tokens=80),
        agent="B",
    )
    stats = t.stats()
    assert "x-ai/grok-4.20" in stats["per_model"]
    assert "anthropic/claude-sonnet-4-20250514" in stats["per_model"]
    assert stats["per_model"]["x-ai/grok-4.20"]["call_count"] == 1


def test_reset_daily_clears_state():
    t = InMemoryCostTracker(daily_budget_usd=100.0)
    t.record(
        TokenUsage(model_id="x-ai/grok-4.20", input_tokens=100, output_tokens=200),
        agent="A",
    )
    assert t.daily_spent_usd() > 0

    t.reset_daily()
    assert t.daily_spent_usd() == 0.0
    stats = t.stats()
    assert stats["per_model"] == {}
    assert stats["per_agent"] == {}


def test_alert_threshold_triggers_once():
    t = InMemoryCostTracker(daily_budget_usd=10.0, alert_threshold_pct=0.5)
    # First call brings us to ~$3 — under 50% threshold of $10
    t.record(TokenUsage(model_id="x-ai/grok-4.20", input_tokens=1_000_000, output_tokens=0), agent="X")
    s1 = t.stats()
    assert s1["alerted"] is False

    # Second call brings us to $6 — past 50% threshold
    t.record(TokenUsage(model_id="x-ai/grok-4.20", input_tokens=1_000_000, output_tokens=0), agent="X")
    s2 = t.stats()
    assert s2["alerted"] is True


def test_null_cost_tracker_records_nothing():
    t = NullCostTracker()
    t.record(
        TokenUsage(model_id="x-ai/grok-4.20", input_tokens=10**9, output_tokens=10**9),
        agent="Test",
    )
    assert t.daily_spent_usd() == 0.0
    assert not t.is_budget_exceeded()


def test_default_rates_cover_project_models():
    """Sanity: project models from default config must have rate entries."""
    expected = [
        "x-ai/grok-4.20",
        "anthropic/claude-sonnet-4-20250514",
        "openai/gpt-4o",
    ]
    for m in expected:
        assert m in DEFAULT_MODEL_RATES, f"missing rate for {m}"


def test_satisfies_contract():
    t: ICostTracker = InMemoryCostTracker()
    assert isinstance(t, ICostTracker)


# --- record_run_metrics helper --------------------------------------------


def test_record_run_metrics_extracts_from_agno_metrics():
    """Simulate an Agno RunOutput.metrics shape and verify extraction."""
    mock_response = SimpleNamespace(
        metrics=SimpleNamespace(
            input_tokens=100,
            output_tokens=200,
            cache_read_tokens=10,
            reasoning_tokens=5,
            cost=0.123,
            details={"x-ai/grok-4.20": object()},
        )
    )
    tracker = InMemoryCostTracker()
    usage = record_run_metrics(
        mock_response,
        tracker=tracker,
        agent_name="Perception",
        fallback_model_id="x-ai/grok-4.20",
        tick=42,
    )
    assert usage is not None
    assert usage.input_tokens == 100
    assert usage.output_tokens == 200
    assert usage.cached_tokens == 10
    assert usage.reasoning_tokens == 5
    # tracker received the call
    assert tracker.daily_spent_usd() == pytest.approx(0.123)


def test_record_run_metrics_returns_none_for_empty_metrics():
    """No tokens used → no record."""
    mock_response = SimpleNamespace(
        metrics=SimpleNamespace(
            input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
        )
    )
    tracker = InMemoryCostTracker()
    usage = record_run_metrics(
        mock_response,
        tracker=tracker,
        agent_name="Test",
        fallback_model_id="x-ai/grok-4.20",
    )
    assert usage is None
    assert tracker.daily_spent_usd() == 0.0


def test_record_run_metrics_handles_missing_metrics_attr():
    """Mocked agent without `.metrics` should not crash."""
    mock_response = SimpleNamespace(content="hello")
    tracker = InMemoryCostTracker()
    usage = record_run_metrics(
        mock_response,
        tracker=tracker,
        agent_name="Test",
        fallback_model_id="x-ai/grok-4.20",
    )
    assert usage is None


# --- AgnoModelInvoker ------------------------------------------------------


def test_agno_model_invoker_success():
    mock_agent = MagicMock()
    mock_response = SimpleNamespace(
        content="result",
        metrics=SimpleNamespace(
            input_tokens=100,
            output_tokens=200,
            reasoning_tokens=0,
            cost=0.05,
            details={"x-ai/grok-4.20": object()},
        ),
    )
    mock_agent.run.return_value = mock_response
    tracker = InMemoryCostTracker()
    invoker = AgnoModelInvoker(
        agent=mock_agent,
        cost_tracker=tracker,
        agent_name="Test",
        primary_model_id="x-ai/grok-4.20",
    )
    result = invoker.invoke("hello")
    assert result.success is True
    assert result.content == "result"
    assert result.usage is not None
    assert result.model_used == "x-ai/grok-4.20"
    assert tracker.daily_spent_usd() > 0


def test_agno_model_invoker_handles_run_exception():
    mock_agent = MagicMock()
    mock_agent.run.side_effect = RuntimeError("boom")
    tracker = InMemoryCostTracker()
    invoker = AgnoModelInvoker(
        agent=mock_agent,
        cost_tracker=tracker,
        agent_name="Test",
        primary_model_id="x-ai/grok-4.20",
    )
    result = invoker.invoke("hello")
    assert result.success is False
    assert "boom" in (result.error or "")
    # No usage recorded on failure
    assert tracker.daily_spent_usd() == 0.0
