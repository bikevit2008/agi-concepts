"""NatsEventBus — distributed `IEventBus` over NATS JetStream.

When `flags.nats_bus_enabled` is on, the loop publishes envelopes to a
JetStream stream and listens via durable consumers. This makes events
durable and replayable across restarts and across multiple processes.

Subjects: every envelope becomes `<stream>.<event_type>`.
Stream name: configured by `bus.stream_name`.
Durable consumer name: `bus.durable_consumer`.

Lazy-imports nats so the rest of the codebase works without it.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

import structlog

from src.bus.event_types import schema_for
from src.contracts.bus import EventEnvelope, EventHandler, IEventBus

logger = structlog.get_logger("consciousness.bus.nats")


@dataclass
class NatsEventBus:
    """JetStream-backed event bus.

    Usage:
        bus = NatsEventBus(nats_url="nats://localhost:4222",
                           stream_name="consciousness",
                           durable_consumer="loop")
        await bus.connect()
        await bus.emit("perception.output", {...})
        ...
        await bus.close()
    """

    nats_url: str = "nats://localhost:4222"
    stream_name: str = "consciousness"
    durable_consumer: str = "consciousness-loop"
    schema_validation: bool = True
    history_size: int = 500

    _nc: Any = None  # nats.aio.client.Client
    _js: Any = None  # JetStream context
    _connected: bool = False
    _subscribers: Dict[str, List[EventHandler]] = field(default_factory=dict)
    _local_history: deque = field(default_factory=lambda: deque(maxlen=500))
    _push_subs: List[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self._local_history.maxlen != self.history_size:
            self._local_history = deque(maxlen=self.history_size)

    async def connect(self) -> bool:
        """Connect + ensure stream exists. Returns True on success."""
        try:
            import nats
        except ImportError:
            logger.error("nats_not_installed")
            return False

        try:
            self._nc = await nats.connect(self.nats_url)
            self._js = self._nc.jetstream()
            # Idempotent stream creation
            subjects = [f"{self.stream_name}.>"]
            try:
                await self._js.add_stream(name=self.stream_name, subjects=subjects)
            except Exception as e:
                # Stream may already exist; that's fine.
                logger.info(
                    "nats_stream_exists_or_warning",
                    stream=self.stream_name,
                    detail=str(e),
                )
            self._connected = True
            logger.info("nats_connected", url=self.nats_url, stream=self.stream_name)
            return True
        except Exception as e:
            logger.error("nats_connect_failed", error=str(e), url=self.nats_url)
            self._connected = False
            return False

    async def close(self) -> None:
        for sub in self._push_subs:
            try:
                await sub.unsubscribe()
            except Exception:
                pass
        try:
            if self._nc is not None:
                await self._nc.close()
        except Exception as e:
            logger.warning("nats_close_warning", error=str(e))
        self._connected = False
        self._nc = None
        self._js = None

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register a handler. Actual NATS sub created on first subscription
        for that event_type. Returns immediately (sub creation is awaitable
        elsewhere via _ensure_subscription)."""
        self._subscribers.setdefault(event_type, []).append(handler)
        # Note: caller should await ensure_subscription(event_type) for
        # NATS-side wiring.

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(handler)
            except ValueError:
                pass

    async def ensure_subscription(self, event_type: str) -> None:
        """Create the JetStream durable consumer for this event_type if not
        already created."""
        if not self._connected or self._js is None:
            return
        subject = f"{self.stream_name}.{event_type}"

        async def cb(msg: Any) -> None:
            try:
                payload = json.loads(msg.data.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.error("nats_decode_failed", error=str(e))
                await msg.ack()
                return

            envelope = EventEnvelope(
                event_type=payload.get("event_type", event_type),
                payload=payload.get("payload", {}),
                source=payload.get("source", "remote"),
                timestamp_ms=int(payload.get("timestamp_ms", 0) or 0),
                schema_version=int(payload.get("schema_version", 1) or 1),
            )
            self._local_history.append(envelope)
            for h in list(self._subscribers.get(event_type, [])):
                try:
                    await h(envelope)
                except Exception as e:
                    logger.error("nats_handler_error", error=str(e))
            try:
                await msg.ack()
            except Exception:
                pass

        try:
            sub = await self._js.subscribe(
                subject=subject,
                durable=f"{self.durable_consumer}-{event_type.replace('.', '-')}",
                stream=self.stream_name,
                cb=cb,
            )
            self._push_subs.append(sub)
        except Exception as e:
            logger.error("nats_subscribe_failed", subject=subject, error=str(e))

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

        self._local_history.append(envelope)

        if not self._connected or self._js is None:
            # Bus is offline — log local-only mode
            return

        subject = f"{self.stream_name}.{envelope.event_type}"
        body = json.dumps(
            {
                "event_type": envelope.event_type,
                "payload": envelope.payload,
                "source": envelope.source,
                "timestamp_ms": envelope.timestamp_ms,
                "schema_version": envelope.schema_version,
            },
            ensure_ascii=False,
        ).encode("utf-8")

        try:
            await self._js.publish(subject=subject, payload=body, stream=self.stream_name)
        except Exception as e:
            logger.error("nats_publish_failed", subject=subject, error=str(e))

    async def emit(
        self,
        event_type: str,
        payload: Dict[str, Any],
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
            return list(self._local_history)[-limit:]
        return [e for e in self._local_history if e.event_type == event_type][-limit:]

    async def replay(
        self,
        event_type: Optional[str] = None,
        since_timestamp_ms: int = 0,
    ) -> Iterable[EventEnvelope]:
        # Local history replay (NATS-side replay is via consumer policy)
        return iter(
            e
            for e in self._local_history
            if (event_type is None or e.event_type == event_type)
            and e.timestamp_ms >= since_timestamp_ms
        )

    @staticmethod
    def _validate(envelope: EventEnvelope) -> None:
        schema = schema_for(envelope.event_type)
        if schema is None:
            return
        try:
            import jsonschema
        except ImportError:
            return
        jsonschema.validate(envelope.payload, schema)


__all__ = ["NatsEventBus"]
