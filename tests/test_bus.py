"""Tests for the event bus subsystem (Stage 8)."""

import asyncio

import pytest

from src.bus.asyncio_bus import AsyncioEventBus
from src.bus.event_types import EventTypes, schema_for
from src.contracts.bus import EventEnvelope, IEventBus, NullEventBus


# --- AsyncioEventBus -------------------------------------------------------


def test_asyncio_bus_publish_subscribe_roundtrip():
    bus = AsyncioEventBus()
    received = []

    async def handler(env: EventEnvelope) -> None:
        received.append(env)

    bus.subscribe(EventTypes.PERCEPTION_OUTPUT, handler)

    async def go() -> None:
        await bus.emit(
            EventTypes.PERCEPTION_OUTPUT,
            {"stimulus_type": "verbal", "content_summary": "hello"},
            source="test",
        )

    asyncio.run(go())

    assert len(received) == 1
    assert received[0].event_type == EventTypes.PERCEPTION_OUTPUT
    assert received[0].payload["stimulus_type"] == "verbal"
    assert received[0].source == "test"


def test_asyncio_bus_history_filtering():
    bus = AsyncioEventBus()

    async def go() -> None:
        await bus.emit(EventTypes.PERCEPTION_OUTPUT, {"stimulus_type": "a"}, source="s")
        await bus.emit(EventTypes.EMOTION_OUTPUT, {"primary_emotion": "joy"}, source="s")
        await bus.emit(EventTypes.PERCEPTION_OUTPUT, {"stimulus_type": "b"}, source="s")

    asyncio.run(go())

    perception_history = bus.history(EventTypes.PERCEPTION_OUTPUT)
    assert len(perception_history) == 2
    all_history = bus.history()
    assert len(all_history) == 3


def test_asyncio_bus_unsubscribe_stops_delivery():
    bus = AsyncioEventBus()
    received = []

    async def handler(env: EventEnvelope) -> None:
        received.append(env)

    bus.subscribe(EventTypes.PERCEPTION_OUTPUT, handler)
    bus.unsubscribe(EventTypes.PERCEPTION_OUTPUT, handler)

    async def go() -> None:
        await bus.emit(EventTypes.PERCEPTION_OUTPUT, {"stimulus_type": "v"})

    asyncio.run(go())
    assert received == []


def test_asyncio_bus_history_bounded():
    bus = AsyncioEventBus(history_size=3)

    async def go() -> None:
        for i in range(10):
            await bus.emit(EventTypes.PERCEPTION_OUTPUT, {"stimulus_type": str(i)})

    asyncio.run(go())
    assert len(bus.history()) == 3


def test_asyncio_bus_handler_exception_does_not_break_bus():
    bus = AsyncioEventBus()
    bad_calls = []
    good_calls = []

    async def bad(env: EventEnvelope) -> None:
        bad_calls.append(env)
        raise RuntimeError("boom")

    async def good(env: EventEnvelope) -> None:
        good_calls.append(env)

    bus.subscribe(EventTypes.PERCEPTION_OUTPUT, bad)
    bus.subscribe(EventTypes.PERCEPTION_OUTPUT, good)

    async def go() -> None:
        await bus.emit(EventTypes.PERCEPTION_OUTPUT, {"stimulus_type": "v"})

    asyncio.run(go())
    assert len(bad_calls) == 1
    assert len(good_calls) == 1


def test_schema_validation_blocks_malformed():
    """When schema_validation=True, missing required fields stop publish."""
    pytest.importorskip("jsonschema")
    bus = AsyncioEventBus(schema_validation=True)
    received = []

    async def handler(env: EventEnvelope) -> None:
        received.append(env)

    bus.subscribe(EventTypes.PERCEPTION_OUTPUT, handler)

    async def go() -> None:
        # Missing required "stimulus_type" — must be rejected
        await bus.emit(EventTypes.PERCEPTION_OUTPUT, {"content_summary": "no type"})

    asyncio.run(go())
    assert received == []


def test_schema_validation_allows_well_formed():
    pytest.importorskip("jsonschema")
    bus = AsyncioEventBus(schema_validation=True)
    received = []

    async def handler(env: EventEnvelope) -> None:
        received.append(env)

    bus.subscribe(EventTypes.PERCEPTION_OUTPUT, handler)

    async def go() -> None:
        await bus.emit(EventTypes.PERCEPTION_OUTPUT, {"stimulus_type": "verbal"})

    asyncio.run(go())
    assert len(received) == 1


def test_unknown_event_type_passes_through_without_schema():
    bus = AsyncioEventBus(schema_validation=True)
    received = []

    async def handler(env: EventEnvelope) -> None:
        received.append(env)

    bus.subscribe("custom.unknown", handler)

    async def go() -> None:
        await bus.emit("custom.unknown", {"any": "thing"})

    asyncio.run(go())
    assert len(received) == 1


def test_replay_filters_by_timestamp():
    bus = AsyncioEventBus()

    async def go() -> None:
        await bus.emit(EventTypes.PERCEPTION_OUTPUT, {"stimulus_type": "a"})
        await bus.emit(EventTypes.PERCEPTION_OUTPUT, {"stimulus_type": "b"})

    asyncio.run(go())
    history = bus.history()
    middle_ts = history[0].timestamp_ms

    async def replay():
        return list(await bus.replay(since_timestamp_ms=middle_ts))

    replayed = asyncio.run(replay())
    assert len(replayed) >= 1


# --- Schemas ---------------------------------------------------------------


def test_schema_for_known_returns_schema():
    s = schema_for(EventTypes.PERCEPTION_OUTPUT)
    assert s is not None
    assert s["type"] == "object"
    assert "stimulus_type" in s["properties"]


def test_schema_for_unknown_returns_none():
    assert schema_for("unknown.event") is None


def test_event_types_constants_unique():
    """All EventTypes constants must be unique strings."""
    consts = [
        v
        for k, v in EventTypes.__dict__.items()
        if not k.startswith("_") and isinstance(v, str)
    ]
    assert len(set(consts)) == len(consts)


# --- Null impl + contract conformance --------------------------------------


def test_null_event_bus_no_op():
    bus = NullEventBus()

    async def go() -> None:
        envelope = await bus.emit("anything", {"foo": "bar"})
        assert envelope.event_type == "anything"
        assert bus.history() == []

    asyncio.run(go())


def test_asyncio_bus_satisfies_contract():
    bus: IEventBus = AsyncioEventBus()
    assert isinstance(bus, IEventBus)
