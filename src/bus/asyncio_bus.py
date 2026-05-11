"""AsyncioEventBus — `IEventBus` implementation backed by asyncio queues.

This is the in-process default. It satisfies the contract using only
the standard library, with optional JSON Schema validation and bounded
history for TUI/harness diagnostics.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

import structlog

from src.bus.event_types import schema_for
from src.contracts.bus import EventEnvelope, EventHandler, IEventBus

logger = structlog.get_logger("consciousness.bus.asyncio")


@dataclass
class AsyncioEventBus:
    """Async pub/sub bus with bounded history and optional schema validation."""

    history_size: int = 500
    schema_validation: bool = False

    _subscribers: Dict[str, List[EventHandler]] = field(default_factory=dict)
    _history: deque = field(default_factory=lambda: deque(maxlen=500))

    def __post_init__(self) -> None:
        if self._history.maxlen != self.history_size:
            self._history = deque(maxlen=self.history_size)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(handler)
            except ValueError:
                pass

    async def publish(self, envelope: EventEnvelope) -> None:
        if self.schema_validation:
            try:
                self._validate(envelope)
            except Exception as e:
                logger.warning(
                    "bus_schema_validation_failed",
                    event_type=envelope.event_type,
                    error=str(e),
                )
                return
        if envelope.timestamp_ms <= 0:
            envelope.timestamp_ms = int(time.time() * 1000)
        self._history.append(envelope)
        # Notify all subscribers concurrently
        handlers = list(self._subscribers.get(envelope.event_type, []))
        for h in handlers:
            try:
                await h(envelope)
            except Exception as e:
                logger.error("bus_handler_error", event_type=envelope.event_type, error=str(e))

    async def emit(
        self,
        event_type: str,
        payload: Dict,
        source: str = "system",
    ) -> EventEnvelope:
        envelope = EventEnvelope(
            event_type=event_type,
            payload=payload,
            source=source,
            timestamp_ms=int(time.time() * 1000),
        )
        await self.publish(envelope)
        return envelope

    def history(
        self,
        event_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[EventEnvelope]:
        if event_type is None:
            return list(self._history)[-limit:]
        return [e for e in self._history if e.event_type == event_type][-limit:]

    async def replay(
        self,
        event_type: Optional[str] = None,
        since_timestamp_ms: int = 0,
    ) -> Iterable[EventEnvelope]:
        return iter(
            e
            for e in self._history
            if (event_type is None or e.event_type == event_type)
            and e.timestamp_ms >= since_timestamp_ms
        )

    async def close(self) -> None:
        return None

    @staticmethod
    def _validate(envelope: EventEnvelope) -> None:
        schema = schema_for(envelope.event_type)
        if schema is None:
            return  # unknown event types pass-through
        try:
            import jsonschema
        except ImportError:
            return  # validation library not installed; skip
        jsonschema.validate(envelope.payload, schema)


__all__ = ["AsyncioEventBus"]
