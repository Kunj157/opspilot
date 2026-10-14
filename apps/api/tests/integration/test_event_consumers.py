"""Consumers: idempotent handling, retries with backoff, and the dead-letter topic."""

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags
from prometheus_client import REGISTRY
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opspilot_api.db.models import ProcessedEvent
from opspilot_api.events.consumer import EventProcessor
from opspilot_api.events.envelope import Envelope
from opspilot_api.events.handlers import investigation_requester
from opspilot_api.events.relay import OutboxRelay
from tests.support.events import (
    LATER,
    Recorder,
    created_event,
    detector_incident,
    investigations,
    reset_relay,
)

pytestmark = pytest.mark.integration


def processor(
    sessions: async_sessionmaker[AsyncSession], producer: Any, *, authoritative: bool = True
) -> EventProcessor:
    return EventProcessor(
        f"investigations-{uuid.uuid4().hex[:6]}",
        sessions,
        investigation_requester(authoritative=authoritative),
        producer,
        backoff=0.01,
    )


async def test_a_duplicate_event_queues_one_investigation(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    incident = await detector_incident(sessions)
    p, message = processor(sessions, Recorder()), created_event(incident)
    delay = "opspilot_event_processing_delay_seconds_count"
    before = REGISTRY.get_sample_value(delay, {"consumer": p.name}) or 0

    first = await p.process("incident.created.v1", b"k", message)
    second = await p.process("incident.created.v1", b"k", message)

    # Only the handled delivery counts towards the processing-delay SLI.
    assert REGISTRY.get_sample_value(delay, {"consumer": p.name}) == before + 1

    assert (first.outcome, first.detail) == ("handled", "queued")
    assert second.outcome == "duplicate"
    assert await investigations(sessions, incident) == 1


async def test_an_event_for_a_resolved_incident_changes_nothing(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    incident = await detector_incident(sessions, resolve=True)

    result = await processor(sessions, Recorder()).process(
        "incident.created.v1", b"k", created_event(incident)
    )

    assert result.detail == "skipped: already resolved"
    assert await investigations(sessions, incident) == 0


async def test_shadow_mode_only_compares_with_the_direct_call(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    incident = await detector_incident(sessions)

    result = await processor(sessions, Recorder(), authoritative=False).process(
        "incident.created.v1", b"k", created_event(incident)
    )

    assert result.detail == "shadow: direct call queued nothing"
    assert await investigations(sessions, incident) == 0


@pytest.mark.parametrize(
    "message",
    [b"not json", b"[1, 2]", b'{"event_id": "x"}'],
    ids=["garbage", "not-an-object", "missing-fields"],
)
async def test_poison_messages_go_to_the_dead_letter_topic(
    sessions: async_sessionmaker[AsyncSession], message: bytes
) -> None:
    recorder = Recorder()

    result = await processor(sessions, recorder).process("incident.created.v1", b"k", message)

    assert result.outcome == "dead_lettered"
    [(topic, _, value, headers)] = recorder.sent
    assert topic == "incident.created.v1.dlq"
    assert value == message
    assert dict(headers)["error"].startswith(b"poison message")


async def test_an_unknown_schema_version_is_parked(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    incident = await detector_incident(sessions)
    recorder = Recorder()

    result = await processor(sessions, recorder).process(
        "incident.created.v1", b"k", created_event(incident, version=2)
    )

    assert result.outcome == "dead_lettered"
    assert await investigations(sessions, incident) == 0


async def test_transient_failures_are_retried_then_parked(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    incident = await detector_incident(sessions)
    calls = 0

    async def flaky(session: AsyncSession, envelope: Envelope) -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectionError("database hiccup")
        return "ok"

    recovered = EventProcessor("flaky", sessions, flaky, Recorder(), backoff=0.01)
    assert (
        await recovered.process("incident.created.v1", b"k", created_event(incident))
    ).outcome == "handled"
    assert calls == 3

    async def broken(session: AsyncSession, envelope: Envelope) -> str:
        raise ConnectionError("still down")

    recorder = Recorder()
    parked = EventProcessor("broken", sessions, broken, recorder, attempts=3, backoff=0.01)
    result = await parked.process("incident.created.v1", b"k", created_event(incident))
    assert result.outcome == "dead_lettered"
    assert "failed 3 times" in (result.detail or "")
    async with sessions() as session:
        assert (
            await session.scalar(
                sa.select(sa.func.count())
                .select_from(ProcessedEvent)
                .where(ProcessedEvent.consumer == "broken")
            )
            == 0
        ), "a failed attempt leaves no idempotency record behind"


TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
TRACEPARENT = f"00-{TRACE_ID}-00f067aa0ba902b7-01".encode()


async def test_handling_continues_the_producers_trace(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    incident = await detector_incident(sessions)
    seen: list[str] = []

    async def handler(session: AsyncSession, envelope: Envelope) -> str:
        seen.append(format(trace.get_current_span().get_span_context().trace_id, "032x"))
        return "ok"

    p = EventProcessor("traced", sessions, handler, Recorder())
    headers = [("event_type", b"incident.created.v1"), ("traceparent", TRACEPARENT)]

    result = await p.process("incident.created.v1", b"k", created_event(incident), headers)

    assert result.outcome == "handled"
    assert seen == [TRACE_ID]


async def test_a_parked_message_keeps_its_trace_context(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    recorder = Recorder()

    await processor(sessions, recorder).process(
        "incident.created.v1", b"k", b"not json", [("traceparent", TRACEPARENT)]
    )

    [(_, _, _, headers)] = recorder.sent
    assert dict(headers)["traceparent"] == TRACEPARENT


async def test_messages_without_trace_headers_are_still_handled(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    incident = await detector_incident(sessions)

    result = await processor(sessions, Recorder()).process(
        "incident.created.v1", b"k", created_event(incident), [("traceparent", b"garbage")]
    )

    assert (result.outcome, result.detail) == ("handled", "queued")


async def test_the_relay_puts_the_active_trace_in_the_headers(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await reset_relay(sessions)
    await detector_incident(sessions)
    recorder = Recorder()
    parent = NonRecordingSpan(
        SpanContext(int(TRACE_ID, 16), 0x00F067AA0BA902B7, False, TraceFlags(1))
    )

    with trace.use_span(parent):
        await OutboxRelay(sessions, recorder).publish_once(LATER)

    [(_, _, _, headers)] = recorder.sent
    assert TRACE_ID in dict(headers)["traceparent"].decode()
