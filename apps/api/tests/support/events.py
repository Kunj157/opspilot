"""Shared fixtures and helpers for the event tests (Redpanda via Testcontainers)."""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from aiokafka import AIOKafkaConsumer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opspilot_api.db.models import (
    ActorType,
    EventRelayCheckpoint,
    Incident,
    IncidentStatus,
    Investigation,
    Organization,
    Severity,
)
from opspilot_api.events.relay import NAME
from opspilot_api.incidents import service as incidents

LATER = datetime.now(UTC) + timedelta(minutes=5)  # past the relay's settle delay


class Recorder:
    """A producer that keeps messages, optionally failing after `fail_after` sends."""

    def __init__(self, fail_after: int | None = None) -> None:
        self.sent: list[tuple[str, bytes, bytes, list[tuple[str, bytes]]]] = []
        self.fail_after = fail_after

    async def send(
        self, topic: str, key: bytes, value: bytes, headers: list[tuple[str, bytes]]
    ) -> None:
        if self.fail_after is not None and len(self.sent) >= self.fail_after:
            raise ConnectionError("broker unavailable")
        self.sent.append((topic, key, value, headers))


async def reset_relay(sessions: async_sessionmaker[AsyncSession]) -> None:
    """Start the relay after everything already in the shared test database."""
    async with sessions() as session:
        top = await session.scalar(
            sa.text("select coalesce(max(sequence), 0) from incident_events")
        )
        await session.execute(sa.delete(EventRelayCheckpoint))
        session.add(EventRelayCheckpoint(name=NAME, last_sequence=int(top or 0)))
        await session.commit()


async def detector_incident(
    sessions: async_sessionmaker[AsyncSession], *, resolve: bool = False
) -> Incident:
    async with sessions() as session:
        org = Organization(name="Acme", slug=f"org-{uuid.uuid4().hex[:10]}")
        session.add(org)
        await session.flush()
        actor = incidents.Actor(ActorType.SYSTEM, "detector:error-rate", org.id)
        incident = await incidents.create_incident(
            session,
            actor,
            title="High error rate on Checkout",
            severity=Severity.HIGH,
            source="detector",
        )
        if resolve:
            for status in (
                IncidentStatus.INVESTIGATING,
                IncidentStatus.MONITORING,
                IncidentStatus.RESOLVED,
            ):
                await incidents.transition(
                    session, incident, status, expected_version=incident.version, actor=actor
                )
        await session.commit()
        return incident


def created_event(incident: Incident, *, version: int = 1) -> bytes:
    return json.dumps(
        {
            "event_id": str(uuid.uuid4()),
            "event_type": "incident.created.v1",
            "event_version": version,
            "organization_id": str(incident.organization_id),
            "correlation_id": str(incident.id),
            "causation_id": None,
            "occurred_at": datetime.now(UTC).isoformat(),
            "producer": "api",
            "payload": {"incident_id": str(incident.id), "source": "detector"},
        }
    ).encode()


async def investigations(sessions: async_sessionmaker[AsyncSession], incident: Incident) -> int:
    async with sessions() as session:
        return int(
            await session.scalar(
                sa.select(sa.func.count())
                .select_from(Investigation)
                .where(Investigation.incident_id == incident.id)
            )
            or 0
        )


async def read_topic(broker: str, topic: str, expect: int, wait: float = 20) -> list[Any]:
    consumer = AIOKafkaConsumer(
        topic, bootstrap_servers=broker, group_id=None, auto_offset_reset="earliest"
    )
    await consumer.start()
    records: list[Any] = []
    try:
        deadline = asyncio.get_running_loop().time() + wait
        while len(records) < expect and asyncio.get_running_loop().time() < deadline:
            batches = await consumer.getmany(timeout_ms=500)
            for batch in batches.values():
                records.extend(batch)
    finally:
        await consumer.stop()
    return records
