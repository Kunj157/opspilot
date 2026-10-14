"""Transactional outbox: the incident timeline, published to the broker in order.

Every incident change already writes a timeline event in its own
transaction, so the timeline is the outbox. The relay reads committed events
after its checkpoint, publishes the ones that map to a topic (keyed by
incident, so one incident's events stay ordered), and advances the
checkpoint only after the broker acknowledged them. If the broker is down,
publishing stops and resumes at the checkpoint, so nothing is lost; a crash
between publish and checkpoint republishes, which consumers ignore by
event ID.

Identity values can commit out of order under concurrency, so only events
older than SETTLE are read; a later-committed lower sequence still arrives
before the relay passes it.
"""

import json
from datetime import UTC, datetime, timedelta

import structlog
from opentelemetry import trace
from opentelemetry.trace import SpanKind
from prometheus_client import Counter
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opspilot_api.db.models import EventRelayCheckpoint, IncidentEvent
from opspilot_api.events.envelope import to_envelope, topic_for
from opspilot_api.events.producer import Producer, trace_headers

log = structlog.get_logger("opspilot.events.relay")

NAME = "incident-timeline"
BATCH = 200
SETTLE = timedelta(seconds=3)
PUBLISHED = Counter("opspilot_events_published_total", "Events published", ["topic"])
tracer = trace.get_tracer("opspilot.events.relay")


class OutboxRelay:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], producer: Producer) -> None:
        self.sessions = sessions
        self.producer = producer

    async def _checkpoint(self, session: AsyncSession) -> int:
        found = await session.scalar(
            select(EventRelayCheckpoint.last_sequence).where(EventRelayCheckpoint.name == NAME)
        )
        return int(found or 0)

    async def _advance(self, sequence: int) -> None:
        async with self.sessions() as session:
            await session.execute(
                insert(EventRelayCheckpoint)
                .values(name=NAME, last_sequence=sequence, updated_at=datetime.now(UTC))
                .on_conflict_do_update(
                    index_elements=["name"],
                    set_={"last_sequence": sequence, "updated_at": datetime.now(UTC)},
                )
            )
            await session.commit()

    async def publish_once(self, now: datetime | None = None) -> int:
        """Publish one batch; returns how many events were sent. Raises if the broker fails."""
        now = now or datetime.now(UTC)
        async with self.sessions() as session:
            after = await self._checkpoint(session)
            events = list(
                await session.scalars(
                    select(IncidentEvent)
                    .where(IncidentEvent.sequence > after, IncidentEvent.created_at < now - SETTLE)
                    .order_by(IncidentEvent.sequence)
                    .limit(BATCH)
                )
            )
        sent, last = 0, after
        try:
            for event in events:
                topic = topic_for(event)
                if topic:
                    envelope = to_envelope(event, topic)
                    # The consumer continues this span from the traceparent header.
                    with tracer.start_as_current_span(
                        f"{topic} publish",
                        kind=SpanKind.PRODUCER,
                        attributes={
                            "messaging.system": "kafka",
                            "messaging.operation.type": "send",
                            "messaging.destination.name": topic,
                        },
                    ):
                        await self.producer.send(
                            topic,
                            key=str(event.incident_id).encode(),
                            value=envelope.model_dump_json().encode(),
                            headers=[("event_type", topic.encode()), *trace_headers()],
                        )
                    PUBLISHED.labels(topic).inc()
                    sent += 1
                last = event.sequence
        finally:
            if last > after:
                await self._advance(last)
        if sent:
            log.info("events published", count=sent, through=last)
        return sent


def decode(value: bytes) -> dict[str, object]:
    """Raw JSON of a message value; raises ValueError for anything else."""
    data = json.loads(value)
    if not isinstance(data, dict):
        raise ValueError("event is not a JSON object")
    return data
