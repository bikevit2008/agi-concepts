"""OpenTelemetry observability collector.

Implements `IObservabilityCollector` over the OTel SDK, with GenAI
semantic conventions baked in (gen_ai.system, gen_ai.request.model,
gen_ai.usage.input_tokens, gen_ai.usage.output_tokens, ...).

The collector creates a `TracerProvider` with an OTLP gRPC exporter
(default endpoint http://localhost:4317; configurable) and a metrics
provider that emits to the same endpoint.

Lazy-imports opentelemetry packages so the rest of the codebase can be
imported on machines without OTel installed.

Usage:
    collector = OtelObservabilityCollector(
        service_name="agi-consciousness",
        otel_endpoint="http://localhost:4317",
    )
    with collector.start_span("agent.run", attributes={"agent.name": "Perception"}) as span:
        span.set_attribute("gen_ai.usage.input_tokens", 100)
        ...
    collector.flush()
    collector.shutdown()
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

import structlog

from src.contracts.observability import (
    IObservabilityCollector,
    ISpan,
    NullObservabilityCollector,
    NullSpan,
)

logger = structlog.get_logger("consciousness.observability")


class _OtelSpanWrapper:
    """Thin adapter from OTel Span to our ISpan protocol.

    We wrap the OTel span as a context manager directly. Our public
    methods accept simple Python types and forward to OTel's API.
    """

    def __init__(self, otel_span_ctx, otel_span) -> None:
        self._ctx = otel_span_ctx
        self._span = otel_span

    def __enter__(self) -> "_OtelSpanWrapper":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        # OTel span's CM auto-records exceptions and ends the span.
        return self._ctx.__exit__(exc_type, exc_val, exc_tb)

    def set_attribute(self, key: str, value: Any) -> None:
        try:
            self._span.set_attribute(key, value)
        except Exception:
            pass

    def set_attributes(self, attrs: Dict[str, Any]) -> None:
        try:
            self._span.set_attributes(attrs)
        except Exception:
            pass

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        try:
            self._span.add_event(name, attributes=attributes or {})
        except Exception:
            pass

    def record_exception(self, exc: BaseException) -> None:
        try:
            self._span.record_exception(exc)
        except Exception:
            pass

    def set_status(self, ok: bool, description: Optional[str] = None) -> None:
        try:
            from opentelemetry.trace import Status, StatusCode

            status = Status(StatusCode.OK if ok else StatusCode.ERROR, description=description)
            self._span.set_status(status)
        except Exception:
            pass


class OtelObservabilityCollector:
    """`IObservabilityCollector` powered by OpenTelemetry."""

    def __init__(
        self,
        service_name: str = "agi-consciousness",
        otel_endpoint: str = "http://localhost:4317",
        gen_ai_system: str = "openrouter",
        disable_exporters: bool = False,
    ) -> None:
        try:
            from opentelemetry import metrics, trace
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
        except ImportError as e:
            raise ImportError(
                "opentelemetry packages are not installed. Install with "
                "`pip install opentelemetry-api opentelemetry-sdk "
                "opentelemetry-exporter-otlp` or use NullObservabilityCollector."
            ) from e

        # GenAI semantic-convention service identification
        resource = Resource.create({"service.name": service_name})

        # Tracer
        tracer_provider = TracerProvider(resource=resource)
        if not disable_exporters:
            try:
                tracer_provider.add_span_processor(
                    BatchSpanProcessor(OTLPSpanExporter(endpoint=otel_endpoint, insecure=True))
                )
            except Exception as e:
                logger.warning(
                    "otel_exporter_init_warning", error=str(e), endpoint=otel_endpoint
                )
        trace.set_tracer_provider(tracer_provider)
        self._tracer = trace.get_tracer(service_name)

        # Meter
        if disable_exporters:
            self._meter = None
        else:
            try:
                metric_reader = PeriodicExportingMetricReader(
                    OTLPMetricExporter(endpoint=otel_endpoint, insecure=True)
                )
                meter_provider = MeterProvider(
                    resource=resource, metric_readers=[metric_reader]
                )
                metrics.set_meter_provider(meter_provider)
                self._meter = metrics.get_meter(service_name)
            except Exception as e:
                logger.warning("otel_meter_init_warning", error=str(e))
                self._meter = None

        self._tracer_provider = tracer_provider
        self._service_name = service_name
        self._gen_ai_system = gen_ai_system
        self._counters: Dict[str, Any] = {}

    def start_span(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> ISpan:
        # Default attributes attached to every span
        attrs: Dict[str, Any] = {"gen_ai.system": self._gen_ai_system}
        if attributes:
            attrs.update(attributes)

        ctx = self._tracer.start_as_current_span(name, attributes=attrs)
        otel_span = ctx.__enter__()
        return _OtelSpanWrapper(otel_span_ctx=ctx, otel_span=otel_span)

    def record_metric(
        self,
        name: str,
        value: float,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self._meter is None:
            return
        counter = self._counters.get(name)
        if counter is None:
            try:
                counter = self._meter.create_counter(name)
            except Exception as e:
                logger.warning("otel_counter_create_failed", name=name, error=str(e))
                return
            self._counters[name] = counter
        try:
            counter.add(value, attributes=attributes or {})
        except Exception:
            pass

    def flush(self, timeout_seconds: float = 5.0) -> None:
        try:
            self._tracer_provider.force_flush(timeout_millis=int(timeout_seconds * 1000))
        except Exception as e:
            logger.warning("otel_flush_warning", error=str(e))

    def shutdown(self) -> None:
        try:
            self._tracer_provider.shutdown()
        except Exception as e:
            logger.warning("otel_shutdown_warning", error=str(e))


__all__ = ["OtelObservabilityCollector"]
