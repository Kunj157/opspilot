"""Consuming events: idempotent handlers, retries with backoff, and a dead-letter topic.

A handler runs in the same database transaction that records the event as
processed for its consumer, so a duplicate, a redelivery after a crash, or a
replay changes nothing. Transient failures are retried with exponential
backoff; a message that keeps failing, or that cannot be parsed or has an
unknown version (a poison message), is parked on `<topic>.dlq` with the
error, and the consumer moves on. Offsets are committed only after a message
is handled or parked.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import structlog
from aiokafka import AIOKafkaConsumer, ConsumerRecord, TopicPartition
from prometheus_client import Counter, Gauge
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opspilot_api.db.models import ProcessedEvent
from opspilot_api.events.envelope import Envelope, dead_letter
from opspilot_api.events.producer import Producer
from opspilot_api.events.relay import decode

log = structlog.get_logger("opspilot.events.consumer")

HANDLED = Counter("opspilot_events_handled_total", "Events handled", ["consumer", "outcome"])
LAG = Gauge(
    "opspilot_consumer_lag",
    "Messages behind the end of the partition",
    ["group", "topic", "partition"],
)

Handler = Callable[[AsyncSession, Envelope], Awaitable[str]]


class PermanentError(Exception):
    """The event can never be handled; retrying is pointless."""


@dataclass(frozen=True)
class Result:
    outcome: str  # handled | duplicate | dead_lettered
    detail: str | None = None


class EventProcessor:
    """Handles one message at a time; separate from the broker client so tests can drive it."""

    def __init__(
        self,
        name: str,
        sessions: async_sessionmaker[AsyncSession],
        handler: Handler,
        producer: Producer,
        *,
        attempts: int = 4,
        backoff: float = 0.5,
    ) -> None:
        self.name = name
        self.sessions = sessions
        self.handler = handler
        self.producer = producer
        self.attempts = attempts
        self.backoff = backoff

    async def _park(self, topic: str, key: bytes | None, value: bytes, error: str) -> Result:
        await self.producer.send(
            dead_letter(topic),
            key=key or b"",
            value=value,
            headers=[("error", error[:500].encode()), ("consumer", self.name.encode())],
        )
        HANDLED.labels(self.name, "dead_lettered").inc()
        log.warning("event dead-lettered", consumer=self.name, topic=topic, error=error)
        return Result("dead_lettered", error)

    async def _once(self, envelope: Envelope, topic: str) -> Result:
        async with self.sessions() as session:
            claimed = await session.execute(
                insert(ProcessedEvent)
                .values(consumer=self.name, event_id=envelope.event_id, topic=topic, outcome="")
                .on_conflict_do_nothing()
                .returning(ProcessedEvent.event_id)
            )
            if claimed.scalar() is None:
                return Result("duplicate")
            outcome = await self.handler(session, envelope)
            await session.execute(
                update(ProcessedEvent)
                .where(
                    ProcessedEvent.consumer == self.name,
                    ProcessedEvent.event_id == envelope.event_id,
                )
                .values(outcome=outcome)
            )
            await session.commit()
            return Result("handled", outcome)

    async def process(self, topic: str, key: bytes | None, value: bytes) -> Result:
        try:
            envelope = Envelope.model_validate(decode(value))
        except (ValueError, ValidationError) as exc:
            return await self._park(topic, key, value, f"poison message: {exc}")
        if envelope.event_type != topic.removesuffix(".dlq"):
            return await self._park(topic, key, value, f"{envelope.event_type} on topic {topic}")
        for attempt in range(1, self.attempts + 1):
            try:
                result = await self._once(envelope, topic)
            except PermanentError as exc:
                return await self._park(topic, key, value, str(exc))
            except Exception as exc:
                if attempt == self.attempts:
                    return await self._park(topic, key, value, f"failed {attempt} times: {exc}")
                await asyncio.sleep(self.backoff * 2 ** (attempt - 1))
                continue
            HANDLED.labels(self.name, result.outcome).inc()
            return result
        raise AssertionError("unreachable")


class KafkaConsumerLoop:
    """A consumer group member feeding messages to an EventProcessor."""

    def __init__(
        self, processor: EventProcessor, bootstrap_servers: str, topics: list[str]
    ) -> None:
        self.processor = processor
        self.topics = topics
        self.consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=bootstrap_servers,
            group_id=processor.name,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )

    async def run(self, stop: asyncio.Event) -> None:
        await self.consumer.start()
        try:
            while not stop.is_set():
                batches = await self.consumer.getmany(timeout_ms=1000, max_records=100)
                for partition, records in batches.items():
                    for record in records:
                        await self._handle(record)
                    await self.consumer.commit()
                    await self._lag(partition)
        finally:
            await self.consumer.stop()

    async def _handle(self, record: ConsumerRecord[bytes, bytes]) -> None:
        await self.processor.process(record.topic, record.key, record.value or b"")

    async def _lag(self, partition: TopicPartition) -> None:
        end = self.consumer.highwater(partition)
        if end is None:
            return
        position = await self.consumer.position(partition)
        LAG.labels(self.processor.name, partition.topic, str(partition.partition)).set(
            max(end - position, 0)
        )
