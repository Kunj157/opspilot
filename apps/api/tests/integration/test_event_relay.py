"""The outbox relay: committed timeline events reach the broker in order, once."""

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opspilot_api.events.envelope import Envelope
from opspilot_api.events.producer import KafkaProducer
from opspilot_api.events.relay import OutboxRelay
from tests.support.events import (
    LATER,
    Recorder,
    detector_incident,
    read_topic,
    reset_relay,
)

pytestmark = pytest.mark.integration


async def test_the_relay_publishes_committed_events_in_order_once(
    sessions: async_sessionmaker[AsyncSession], producer: KafkaProducer, broker: str
) -> None:
    await reset_relay(sessions)
    incident = await detector_incident(sessions, resolve=True)
    relay = OutboxRelay(sessions, producer)

    first = await relay.publish_once(LATER)
    again = await relay.publish_once(LATER)

    assert first == 2  # created and resolved; plain status changes are not topics
    assert again == 0
    created = [
        Envelope.model_validate_json(r.value)
        for r in await read_topic(broker, "incident.created.v1", 1)
        if r.key == str(incident.id).encode()
    ]
    resolved = await read_topic(broker, "incident.resolved.v1", 1)
    assert created[0].correlation_id == incident.id
    assert created[0].payload["source"] == "detector"
    assert "title" not in created[0].payload
    assert any(Envelope.model_validate_json(r.value).payload["to"] == "RESOLVED" for r in resolved)


async def test_events_still_settling_wait_for_the_next_round(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await reset_relay(sessions)
    await detector_incident(sessions)
    recorder = Recorder()

    assert await OutboxRelay(sessions, recorder).publish_once(datetime.now(UTC)) == 0
    assert await OutboxRelay(sessions, recorder).publish_once(LATER) == 1


async def test_a_broker_outage_loses_and_duplicates_nothing(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await reset_relay(sessions)
    for _ in range(3):
        await detector_incident(sessions)
    flaky = Recorder(fail_after=1)

    with pytest.raises(ConnectionError):
        await OutboxRelay(sessions, flaky).publish_once(LATER)
    healthy = Recorder()
    await OutboxRelay(sessions, healthy).publish_once(LATER)

    published = [json.loads(v)["event_id"] for _, _, v, _ in flaky.sent + healthy.sent]
    assert len(published) == 3
    assert len(set(published)) == 3
