"""NATS JetStream integration tests via testcontainers.

Auto-skipped when Docker isn't running (see conftest.py).

These tests:
  - spin up `nats:2-alpine` with `-js` flag (JetStream enabled)
  - validate publish + durable subscribe round-trip
  - exercise schema validation pathway
"""

from __future__ import annotations

import asyncio

import pytest

# Skip the whole module if optional deps are missing.
nats = pytest.importorskip("nats")
testcontainers = pytest.importorskip("testcontainers.core")

from testcontainers.core.container import DockerContainer  # noqa: E402
from testcontainers.core.waiting_utils import wait_for_logs  # noqa: E402

from src.bus.event_types import EventTypes  # noqa: E402
from src.bus.nats_bus import NatsEventBus  # noqa: E402
from src.contracts.bus import EventEnvelope  # noqa: E402

pytestmark = pytest.mark.docker


@pytest.fixture(scope="module")
def nats_container():
    """JetStream-enabled NATS container, shared across this module."""
    container = (
        DockerContainer("nats:2-alpine")
        .with_command("-js")
        .with_exposed_ports(4222)
    )
    container.start()
    try:
        wait_for_logs(container, "Server is ready", timeout=30)
        yield container
    finally:
        container.stop()


def _nats_uri(container) -> str:
    host = container.get_container_host_ip()
    port = container.get_exposed_port(4222)
    return f"nats://{host}:{port}"


def test_nats_bus_connect_and_publish(nats_container):
    """Connect, publish one event, replay from local history."""
    uri = _nats_uri(nats_container)
    bus = NatsEventBus(
        nats_url=uri,
        stream_name="test_consciousness",
        durable_consumer="test-consumer",
        schema_validation=True,
    )

    async def go():
        ok = await bus.connect()
        assert ok, "NATS connect failed"
        try:
            envelope = await bus.emit(
                EventTypes.PERCEPTION_OUTPUT,
                {"stimulus_type": "verbal", "content_summary": "hi"},
                source="test",
            )
            assert envelope.event_type == EventTypes.PERCEPTION_OUTPUT
            local = bus.history()
            assert any(e.event_type == EventTypes.PERCEPTION_OUTPUT for e in local)
        finally:
            await bus.close()

    asyncio.run(go())


def test_nats_bus_subscribe_receives_published(nats_container):
    """Two NatsEventBus instances → publisher + subscriber."""
    uri = _nats_uri(nats_container)
    publisher = NatsEventBus(
        nats_url=uri,
        stream_name="test_consciousness2",
        durable_consumer="pub",
        schema_validation=False,
    )
    subscriber = NatsEventBus(
        nats_url=uri,
        stream_name="test_consciousness2",
        durable_consumer="sub",
        schema_validation=False,
    )
    received: list = []

    async def handler(envelope: EventEnvelope):
        received.append(envelope)

    async def go():
        assert await subscriber.connect()
        assert await publisher.connect()
        try:
            subscriber.subscribe(EventTypes.EMOTION_OUTPUT, handler)
            await subscriber.ensure_subscription(EventTypes.EMOTION_OUTPUT)
            # Brief delay to let consumer wire up
            await asyncio.sleep(0.5)

            await publisher.emit(
                EventTypes.EMOTION_OUTPUT,
                {"primary_emotion": "joy", "intensity": 0.7},
                source="test_pub",
            )

            # Wait up to 5s for delivery
            for _ in range(50):
                if received:
                    break
                await asyncio.sleep(0.1)

            assert len(received) >= 1
            assert received[0].event_type == EventTypes.EMOTION_OUTPUT
            assert received[0].payload["primary_emotion"] == "joy"
        finally:
            await subscriber.close()
            await publisher.close()

    asyncio.run(go())


def test_nats_bus_schema_validation_rejects_malformed(nats_container):
    """schema_validation=True should drop malformed payloads at publish time."""
    uri = _nats_uri(nats_container)
    bus = NatsEventBus(
        nats_url=uri,
        stream_name="test_consciousness3",
        durable_consumer="sv",
        schema_validation=True,
    )

    async def go():
        assert await bus.connect()
        try:
            # Missing required `stimulus_type` for perception.output
            await bus.emit(EventTypes.PERCEPTION_OUTPUT, {"foo": "bar"})
            # Local history should be empty (rejected before publish)
            assert bus.history(EventTypes.PERCEPTION_OUTPUT) == []
        finally:
            await bus.close()

    asyncio.run(go())
