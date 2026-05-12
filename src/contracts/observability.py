"""Observability contracts — spans + metrics emission.

Designed to be a thin wrapper over OpenTelemetry's Tracer API. We define
our own ISpan / IObservabilityCollector so the codebase doesn't depend
directly on opentelemetry-api in places where it's optional.

Aligned with OTel GenAI semantic conventions (gen_ai.system,
gen_ai.request.model, gen_ai.usage.input_tokens, etc.).
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Dict, Optional, Protocol, runtime_checkable


@runtime_checkable
class ISpan(Protocol, AbstractContextManager):
    """A single trace span.

    Mirrors the subset of OTel's Span API that we actually use.
    Implementations should be context-managers so callers can write:

        with collector.start_span("agent.run") as span:
            span.set_attribute("agent.name", "Perception")
            ...
    """

    def set_attribute(self, key: str, value: Any) -> None: ...

    def set_attributes(self, attrs: Dict[str, Any]) -> None: ...

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> None: ...

    def record_exception(self, exc: BaseException) -> None: ...

    def set_status(self, ok: bool, description: Optional[str] = None) -> None: ...


@runtime_checkable
class IObservabilityCollector(Protocol):
    """Top-level observability facade.

    - start_span() yields a context-managed span
    - record_metric() emits a counter / gauge value
    - flush() blocks until pending spans / metrics are exported
    """

    def start_span(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> ISpan: ...

    def record_metric(
        self,
        name: str,
        value: float,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None: ...

    def flush(self, timeout_seconds: float = 5.0) -> None: ...

    def shutdown(self) -> None: ...


# ---------------------------------------------------------------------------
# Null implementations (Null Object Pattern)
# ---------------------------------------------------------------------------


class NullSpan:
    """No-op span: discards everything, returns self for chaining."""

    def __enter__(self) -> "NullSpan":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        return None

    def set_attribute(self, key: str, value: Any) -> None:
        return None

    def set_attributes(self, attrs: Dict[str, Any]) -> None:
        return None

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        return None

    def record_exception(self, exc: BaseException) -> None:
        return None

    def set_status(self, ok: bool, description: Optional[str] = None) -> None:
        return None


class NullObservabilityCollector:
    """No-op collector: emits nothing."""

    _null_span: NullSpan = NullSpan()

    def start_span(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> ISpan:
        return self._null_span

    def record_metric(
        self,
        name: str,
        value: float,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        return None

    def flush(self, timeout_seconds: float = 5.0) -> None:
        return None

    def shutdown(self) -> None:
        return None
