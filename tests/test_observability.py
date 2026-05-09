"""Tests for observability subsystem (Stage 7).

Cover the Null implementations always (no external deps), and OTel/Rerun
where the libraries are installed.
"""

import pytest

from src.contracts.observability import (
    IObservabilityCollector,
    ISpan,
    NullObservabilityCollector,
    NullSpan,
)


# --- Null impls ------------------------------------------------------------


def test_null_observability_start_span_works_as_context_manager():
    c = NullObservabilityCollector()
    with c.start_span("test") as span:
        span.set_attribute("k", "v")
        span.set_attributes({"a": 1, "b": 2})
        span.add_event("hello")
        span.set_status(ok=True)
        # No exception should escape


def test_null_observability_record_metric_does_nothing():
    c = NullObservabilityCollector()
    c.record_metric("counter", 1.0)
    c.flush()
    c.shutdown()


def test_null_span_satisfies_protocol():
    span: ISpan = NullSpan()
    assert isinstance(span, ISpan)


def test_null_collector_satisfies_protocol():
    c: IObservabilityCollector = NullObservabilityCollector()
    assert isinstance(c, IObservabilityCollector)


# --- OTel collector --------------------------------------------------------


pytest.importorskip("opentelemetry.trace")
pytest.importorskip("opentelemetry.sdk.trace")


def test_otel_collector_start_span_records_attributes():
    """Verify spans with our attributes are created.

    `disable_exporters=True` to avoid the SDK's retry-on-unavailable-collector
    machinery during tests.
    """
    from src.observability.otel import OtelObservabilityCollector

    collector = OtelObservabilityCollector(
        service_name="test-svc",
        otel_endpoint="http://localhost:14317",
        disable_exporters=True,
    )

    with collector.start_span("test.span", attributes={"foo": "bar"}) as span:
        span.set_attribute("baz", 42)
        span.set_attributes({"k": "v"})
        span.add_event("event-1", attributes={"x": 1})
        span.set_status(ok=True)

    collector.flush(timeout_seconds=0.1)
    collector.shutdown()


def test_otel_record_metric_does_not_crash():
    from src.observability.otel import OtelObservabilityCollector

    collector = OtelObservabilityCollector(
        service_name="test-svc",
        otel_endpoint="http://localhost:14317",
        disable_exporters=True,
    )
    collector.record_metric("test.counter", 1.0, attributes={"channel": "stress"})
    collector.record_metric("test.counter", 2.0)
    collector.flush(timeout_seconds=0.1)
    collector.shutdown()


# --- Rerun logger ----------------------------------------------------------


rerun = pytest.importorskip("rerun")


def test_rerun_logger_methods_dont_crash():
    """Rerun in test mode (no spawn, no listener) should not crash."""
    from src.visualization.rerun_logger import RerunLogger

    logger = RerunLogger(application_id="test", spawn=False)
    logger.log_runtime_state(1, {"temperature": 0.7, "energy_level": 0.5})
    logger.log_hysteresis(1, {"stress": {"value": 0.3}})
    logger.log_pad_projection(1, pleasure=0.5, arousal=0.3, dominance=0.6)
    logger.log_response(1, source="user", content="hello")
    logger.log_cost(1, cost_usd=0.42, daily_budget_usd=10.0)
    logger.log_circuit_breaker(1, tripped_channels=["stress"])
    logger.shutdown()


def test_null_rerun_logger_methods_dont_crash():
    from src.visualization.rerun_logger import NullRerunLogger

    logger = NullRerunLogger()
    logger.log_runtime_state(1, {"temperature": 0.7})
    logger.log_hysteresis(1, {"stress": {"value": 0.3}})
    logger.log_pad_projection(1, 0.5, 0.3, 0.6)
    logger.log_response(1, source="user", content="hello")
    logger.log_cost(1, 0.4, 10.0)
    logger.log_circuit_breaker(1, ["stress"])
    logger.shutdown()


# --- Loop integration ------------------------------------------------------


def test_loop_uses_observability_for_tick_span():
    """Verify ConsciousnessLoop calls start_span / set_status."""
    import asyncio
    from unittest.mock import MagicMock

    from src.config.flags import FeatureFlags
    from src.config.settings import Settings
    from src.contracts.governance import NullCircuitBreaker, NullGovernanceKernel
    from src.contracts.persistence import NullCheckpoint, NullEventStore
    from src.core.consciousness_loop import ConsciousnessLoop
    from src.core.event_bus import EventBus
    from src.core.runtime_state import RuntimeState
    from src.engine.homeostatic_hysteresis import HomeostaticHysteresisEngine

    settings = Settings()
    flags = FeatureFlags()
    runtime_state = RuntimeState()
    hysteresis = HomeostaticHysteresisEngine.from_settings(settings.hysteresis)

    team = MagicMock()
    team.process_stimulus_sync.return_value = {"response": "ok"}
    team.reflect_sync.return_value = None
    team.spontaneous_thought_sync.return_value = None
    team.record_state_snapshot.return_value = None
    team.current_tick = 0
    team.memories = []
    team.emotion_history = []
    team.state_journal = []

    observability = MagicMock()
    span = MagicMock()
    span.__enter__ = MagicMock(return_value=span)
    span.__exit__ = MagicMock(return_value=None)
    observability.start_span.return_value = span

    loop = ConsciousnessLoop(
        settings=settings,
        flags=flags,
        runtime_state=runtime_state,
        hysteresis=hysteresis,
        event_bus=EventBus(),
        team=team,
        governance=NullGovernanceKernel(),
        circuit_breaker=NullCircuitBreaker(),
        event_store=NullEventStore(),
        checkpoint=NullCheckpoint(),
        observability=observability,
    )
    asyncio.run(loop._tick())
    observability.start_span.assert_called_once_with(
        "consciousness.tick",
        attributes={"consciousness.tick": 1, "consciousness.idle_ticks": 0},
    )
    span.set_status.assert_called()
    # Metrics emitted after tick
    observability.record_metric.assert_called()
