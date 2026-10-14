"""Consuming events: idempotent handlers, retries with backoff, and a dead-letter topic.

A handler runs in the same database transaction that records the event as
processed for its consumer, so a duplicate, a redelivery after a crash, or a
replay changes nothing. Transient failures are retried with exponential
backoff; a message that keeps failing, or that cannot be parsed or has an
unknown version (a poison message), is parked on `<topic>.dlq` with the
error, and the consumer moves on. Offsets are committed only after a message
is handled or parked.

Each message continues the W3C trace context its producer put in the
headers (traceparent, tracestate): handling runs in a consumer span that is
a child of the publishing span, the trace id is bound to every log line,
and a parked message keeps the headers so a replay continues the trace.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from aiokafka import AIOKafkaConsumer, ConsumerRecord, TopicPartition
from opentelemetry import propagate, trace
from opentelemetry.trace import SpanKind
from prometheus_client import Counter, Gauge
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opspilot_api.db.models import ProcessedEvent
from opspilot_api.events.envelope import Envelope, dead_letter
from opspilot_api.events.producer import Producer
from opspilot_api.events.relay import decode
from opspilot_api.ops_metrics import EVENT_DELAY

log = structlog.get_logger("opspilot.events.consumer")

HANDLED = Counter("opspilot_events_handled_total", "Events handled", ["consumer", "outcome"])
LAG = Gauge(
    "opspilot_consumer_lag",
    "Messages behind the end of the partition",
    ["group", "topic", "partition"],
)

Handler = Callable[[AsyncSession, Envelope], Awaitable[str]]
Headers = list[tuple[str, bytes]]
TRACE_HEADERS = {"traceparent", "tracestate", "baggage"}
tracer = trace.get_tracer("opspilot.events.consumer")


def trace_carrier(headers: Headers | None) -> dict[str, str]:
    """The W3C trace context fields of a message's headers."""
    carrier: dict[str, str] = {}
    for key, value in headers or []:
        if key.lower() in TRACE_HEADERS and value:
            try:
                carrier[key.lower()] = value.decode()
            except UnicodeDecodeError:
                continue
    return carrier


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

    async def _park(
        self, topic: str, key: bytes | None, value: bytes, error: str, carrier: dict[str, str]
    ) -> Result:
        await self.producer.send(
            dead_letter(topic),
            key=key or b"",
            value=value,
            headers=[
                ("error", error[:500].encode()),
                ("consumer", self.name.encode()),
                *((k, v.encode()) for k, v in carrier.items()),
            ],
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

    async def process(
        self, topic: str, key: bytes | None, value: bytes, headers: Headers | None = None
    ) -> Result:
        carrier = trace_carrier(headers)
        with tracer.start_as_current_span(
            f"{topic.removesuffix('.dlq')} process",
            context=propagate.extract(carrier),
            kind=SpanKind.CONSUMER,
            attributes={
                "messaging.system": "kafka",
                "messaging.operation.type": "process",
                "messaging.destination.name": topic,
                "messaging.consumer.group.name": self.name,
            },
        ) as span:
            context = span.get_span_context()
            trace_id = format(context.trace_id, "032x") if context.is_valid else None
            with structlog.contextvars.bound_contextvars(trace_id=trace_id):
                return await self._process(topic, key, value, carrier)

    async def _process(
        self, topic: str, key: bytes | None, value: bytes, carrier: dict[str, str]
    ) -> Result:
        try:
            envelope = Envelope.model_validate(decode(value))
        except (ValueError, ValidationError) as exc:
            return await self._park(topic, key, value, f"poison message: {exc}", carrier)
        if envelope.event_type != topic.removesuffix(".dlq"):
            return await self._park(
                topic, key, value, f"{envelope.event_type} on topic {topic}", carrier
            )
        for attempt in range(1, self.attempts + 1):
            try:
                result = await self._once(envelope, topic)
            except PermanentError as exc:
                return await self._park(topic, key, value, str(exc), carrier)
            except Exception as exc:
                if attempt == self.attempts:
                    return await self._park(
                        topic, key, value, f"failed {attempt} times: {exc}", carrier
                    )
                await asyncio.sleep(self.backoff * 2 ** (attempt - 1))
                continue
            HANDLED.labels(self.name, result.outcome).inc()
            if result.outcome == "handled":
                EVENT_DELAY.labels(self.name).observe(
                    max((datetime.now(UTC) - envelope.occurred_at).total_seconds(), 0.0)
                )
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
        await self.processor.process(
            record.topic, record.key, record.value or b"", list(record.headers or [])
        )

    async def _lag(self, partition: TopicPartition) -> None:
        end = self.consumer.highwater(partition)
        if end is None:
            return
        position = await self.consumer.position(partition)
        LAG.labels(self.processor.name, partition.topic, str(partition.partition)).set(
            max(end - position, 0)
        )
