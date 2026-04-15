from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional
from uuid import uuid4


class EventType(Enum):
    STIMULUS = "stimulus"
    EMOTION_CHANGE = "emotion"
    MEMORY_RECALL = "memory_recall"
    PLAN_UPDATE = "plan_update"
    RUNTIME_CHANGE = "runtime"
    STATE_SNAPSHOT = "snapshot"
    FLAG_TOGGLE = "flag_toggle"
    TICK = "tick"
    AGENT_RESPONSE = "agent_response"


@dataclass
class Event:
    type: EventType
    data: Dict[str, Any]
    source: str = "system"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    id: str = field(default_factory=lambda: uuid4().hex[:12])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "source": self.source,
            "data": self.data,
            "timestamp": self.timestamp,
        }


EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """Async pub/sub event bus for inter-component communication.

    Components subscribe to event types and receive events asynchronously.
    The bus also maintains a bounded event history for debugging/logging.
    """

    def __init__(self, history_size: int = 200) -> None:
        self._subscribers: Dict[EventType, List[EventHandler]] = {}
        self._history: List[Event] = []
        self._history_size = history_size
        self._queue: asyncio.Queue[Event] = asyncio.Queue()

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        handlers = self._subscribers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    async def publish(self, event: Event) -> None:
        """Publish an event: store in history and notify all subscribers."""
        self._history.append(event)
        if len(self._history) > self._history_size:
            self._history = self._history[-self._history_size :]

        handlers = self._subscribers.get(event.type, [])
        if handlers:
            await asyncio.gather(*(h(event) for h in handlers), return_exceptions=True)

    async def emit(self, event_type: EventType, data: Dict[str, Any], source: str = "system") -> Event:
        """Convenience: create and publish an event in one call."""
        event = Event(type=event_type, data=data, source=source)
        await self.publish(event)
        return event

    def get_history(self, event_type: Optional[EventType] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent events, optionally filtered by type."""
        events = self._history
        if event_type:
            events = [e for e in events if e.type == event_type]
        return [e.to_dict() for e in events[-limit:]]

    def clear_history(self) -> None:
        self._history.clear()
