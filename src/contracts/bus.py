"""Bus contracts — typed publish/subscribe message bus.

Two implementations:
1. AsyncioEventBus — in-process, async, bounded history. Used by default.
2. NatsEventBus (Stage 8) — distributed, durable, replayable. Used in
   production deployments.

Both satisfy IEventBus, so subscribers don't care which one is wired in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Protocol,
    runtime_checkable,
)


@dataclass
class EventEnvelope:
    """Typed wrapper around an event payload.

    Adds metadata (event_type, source, timestamp) so subscribers can
    filter without inspecting payloads.
    """

    event_type: str
    payload: Dict[str, Any]
    source: str = "system"
    timestamp_ms: int = 0
    schema_version: int = 1


# Async event handler signature — must be awaitable.
EventHandler = Callable[[EventEnvelope], Awaitable[None]]


@runtime_checkable
class IEventBus(Protocol):
    """Async pub/sub bus with history + optional persistence.

    Subscribers register by event_type; handlers receive EventEnvelopes.
    """

    def subscribe(self, event_type: str, handler: EventHandler) -> None: ...

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None: ...

    async def publish(self, envelope: EventEnvelope) -> None: ...

    async def emit(
        self,
        event_type: str,
        payload: Dict[str, Any],
        source: str = "system",
    ) -> EventEnvelope: ...

    def history(
        self,
        event_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[EventEnvelope]: ...

    async def replay(
        self,
        event_type: Optional[str] = None,
        since_timestamp_ms: int = 0,
    ) -> Iterable[EventEnvelope]: ...

    async def close(self) -> None: ...


# ---------------------------------------------------------------------------
# Null implementation (Null Object Pattern)
# ---------------------------------------------------------------------------


class NullEventBus:
    """No-op bus: drops all events, no subscribers ever fire."""

    async def publish(self, envelope: EventEnvelope) -> None:
        return None

    async def emit(
        self,
        event_type: str,
        payload: Dict[str, Any],
        source: str = "system",
    ) -> EventEnvelope:
        return EventEnvelope(event_type=event_type, payload=payload, source=source)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        return None

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        return None

    def history(
        self,
        event_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[EventEnvelope]:
        return []

    async def replay(
        self,
        event_type: Optional[str] = None,
        since_timestamp_ms: int = 0,
    ) -> Iterable[EventEnvelope]:
        return iter([])

    async def close(self) -> None:
        return None
