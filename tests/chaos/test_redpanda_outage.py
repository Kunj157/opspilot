"""Redpanda down: the outbox keeps every event, the relay resumes, consumers see each once."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from opspilot_api.db.models import ActorType, IncidentEvent, Organization, Severity
from opspilot_api.events.consumer import EventProcessor
from opspilot_api.events.envelope import Envelope
from opspilot_api.events.producer import KafkaProducer
from opspilot_api.events.relay import OutboxRelay
from opspilot_api.incidents import service as incidents
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.support.events import read_topic, reset_relay

from chaos.harness import Controlled

TOPIC = "incident.created.v1"


@pytest.fixture
async def sessions(postgres: Controlled) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(postgres.url, pool_pre_ping=True)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def create_incidents(sessions: async_sessionmaker[AsyncSession], count: int) -> list[str]:
    """New incidents; returns the IDs of their incident.created timeline events."""
    async with sessions() as session:
        org = Organization(name="Chaos", slug=f"org-{uuid.uuid4().hex[:10]}")
        session.add(org)
        await session.flush()
        actor = incidents.Actor(ActorType.SYSTEM, "chaos", org.id)
        created = [
            await incidents.create_incident(
                session, actor, title=f"Outage {i}", severity=Severity.HIGH, source="manual"
            )
            for i in range(count)
        ]
        await session.commit()
        from sqlalchemy import select

        ids = await session.scalars(
            select(IncidentEvent.id).where(
                IncidentEvent.incident_id.in_([i.id for i in created]),
                IncidentEvent.event_type == "incident.created",
            )
        )
        return [str(i) for i in ids]


def later() -> datetime:
    return datetime.now(UTC) + timedelta(minutes=1)  # past the relay's settle delay


async def test_no_event_is_lost_or_handled_twice_across_a_broker_outage(
    sessions: async_sessionmaker[AsyncSession], redpanda: Controlled
) -> None:
    await reset_relay(sessions)
    producer = KafkaProducer(redpanda.url)
    relay = OutboxRelay(sessions, producer)
    try:
        expected = await create_incidents(sessions, 3)
        assert await relay.publish_once(later()) == 3

        redpanda.pause()
        try:
            expected += await create_incidents(sessions, 3)
            with pytest.raises(Exception):  # noqa: B017, PT011 - any broker error
                await asyncio.wait_for(relay.publish_once(later()), 60)
            expected += await create_incidents(sessions, 2)
        finally:
            redpanda.unpause()

        # The relay resumes at its checkpoint on its normal loop.
        resumed = 0
        for _ in range(30):
            try:
                sent = await relay.publish_once(later())
            except Exception:
                await asyncio.sleep(1)
                continue
            resumed += sent
            if sent == 0 and resumed:
                break
        assert resumed >= 5
    finally:
        await producer.aclose()

    records = await read_topic(redpanda.url, TOPIC, expect=len(expected), wait=30)
    published = [Envelope.model_validate_json(r.value).event_id for r in records]
    assert {str(e) for e in published} >= set(expected), "an event was lost"

    # Redelivery is allowed (at least once); consumers dedupe by event ID.
    handled: list[uuid.UUID] = []

    async def handler(session: AsyncSession, envelope: Envelope) -> str:
        handled.append(envelope.event_id)
        return "ok"

    processor = EventProcessor("chaos-outage", sessions, handler, producer=None)  # type: ignore[arg-type]
    for record in records:
        await processor.process(TOPIC, record.key, record.value)
    assert sorted(str(e) for e in handled) == sorted(set(str(e) for e in published))
