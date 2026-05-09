"""Event bus subsystem.

Two implementations of `IEventBus`:
- AsyncioEventBus — in-process, no external services. Default.
- NatsEventBus — JetStream-backed, for distributed deployments.

Both support optional JSON Schema validation (jsonschema package).
"""

from src.bus.asyncio_bus import AsyncioEventBus
from src.bus.event_types import EVENT_SCHEMAS, EventTypes, schema_for
from src.bus.nats_bus import NatsEventBus

__all__ = [
    "AsyncioEventBus",
    "EVENT_SCHEMAS",
    "EventTypes",
    "NatsEventBus",
    "schema_for",
]
