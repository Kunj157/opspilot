"""Restart and replay: a consumer group resumes after its offset; replays change nothing."""

import asyncio
import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opspilot_api.db.models import Incident
from opspilot_api.events.consumer import EventProcessor, KafkaConsumerLoop
from opspilot_api.events.handlers import investigation_requester
from opspilot_api.events.producer import KafkaProducer
from opspilot_api.events.replay import replay
from tests.support.events import (
    created_event,
    detector_incident,
    investigations,
    read_topic,
)

pytestmark = pytest.mark.integration


def processor(sessions: async_sessionmaker[AsyncSession], producer: Any) -> EventProcessor:
    return EventProcessor(
        f"investigations-{uuid.uuid4().hex[:6]}",
        sessions,
        investigation_requester(authoritative=True),
        producer,
        backoff=0.01,
    )


async def test_a_restarted_consumer_resumes_and_replays_change_nothing(
    sessions: async_sessionmaker[AsyncSession], producer: KafkaProducer, broker: str
) -> None:
    topic = "incident.created.v1"
    first, second = await detector_incident(sessions), await detector_incident(sessions)
    p = processor(sessions, producer)

    async def run_until(done: Any) -> None:
        stop = asyncio.Event()
        loop = KafkaConsumerLoop(p, broker, [topic])
        task = asyncio.create_task(loop.run(stop))
        for _ in range(100):
            if await done():
                break
            await asyncio.sleep(0.2)
        stop.set()
        await task

    await producer.send(topic, str(first.id).encode(), created_event(first), [])
    await run_until(lambda: _has(sessions, first))
    # Restart: a new member of the same group continues after the committed offset.
    await producer.send(topic, str(second.id).encode(), created_event(second), [])
    await run_until(lambda: _has(sessions, second))

    replayed = await replay(broker, producer, topic)
    await run_until(lambda: _settled())

    assert replayed >= 2
    assert await investigations(sessions, first) == 1
    assert await investigations(sessions, second) == 1


async def _has(sessions: async_sessionmaker[AsyncSession], incident: Incident) -> bool:
    return await investigations(sessions, incident) > 0


async def _settled() -> bool:
    await asyncio.sleep(2)
    return True


async def test_replaying_the_dead_letter_topic_processes_parked_events_once(
    sessions: async_sessionmaker[AsyncSession], producer: KafkaProducer, broker: str
) -> None:
    topic = "incident.created.v1"
    incident = await detector_incident(sessions)
    message = created_event(incident)
    # Parked earlier, e.g. while the database was down.
    await producer.send(f"{topic}.dlq", b"k", message, [("error", b"failed 4 times")])

    for _ in range(2):
        await replay(broker, producer, topic, from_dlq=True)
    p = processor(sessions, producer)
    records = await read_topic(broker, topic, expect=1)
    for record in records:
        await p.process(topic, record.key, record.value)

    assert await investigations(sessions, incident) == 1
