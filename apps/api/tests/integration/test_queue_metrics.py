"""Queue gauges read from the database: depth and oldest age per queue."""

import uuid
from datetime import UTC, datetime, timedelta

from prometheus_client import REGISTRY
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opspilot_api.db.models import Investigation, InvestigationStatus
from opspilot_api.ops_metrics import sample_queues


def gauge(name: str, queue: str) -> float:
    return REGISTRY.get_sample_value(name, {"queue": queue}) or 0.0


async def test_queued_investigations_set_depth_and_age(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    from tests.integration.test_investigation import setup

    # Other tests share the database: measure what this test adds.
    await sample_queues(sessions)
    before = gauge("opspilot_queue_depth", "investigations")
    investigation_id: uuid.UUID = await setup(sessions)
    async with sessions() as session:
        await session.execute(
            update(Investigation)
            .where(Investigation.id == investigation_id)
            .values(
                status=InvestigationStatus.QUEUED,
                created_at=datetime.now(UTC) - timedelta(hours=1),
            )
        )
        await session.commit()

    await sample_queues(sessions, outbox=True)

    assert gauge("opspilot_queue_depth", "investigations") == before + 1
    assert gauge("opspilot_queue_oldest_age_seconds", "investigations") >= 3600
    assert REGISTRY.get_sample_value("opspilot_queue_depth", {"queue": "event_outbox"}) is not None
    async with sessions() as session:
        await session.execute(
            update(Investigation)
            .where(Investigation.id == investigation_id)
            .values(status=InvestigationStatus.FAILED)
        )
        await session.commit()
