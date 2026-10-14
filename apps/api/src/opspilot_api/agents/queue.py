"""Investigations as a durable job queue in PostgreSQL.

A worker claims one queued investigation (or one whose lease expired, e.g.
after a crash) with SELECT ... FOR UPDATE SKIP LOCKED, so concurrent
workers never take the same job and a dead worker's job is retried.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opspilot_api.db.models import ActorType, Incident, Investigation, InvestigationStatus
from opspilot_api.incidents.service import Actor, note

MAX_ATTEMPTS = 3
ACTIVE = (InvestigationStatus.QUEUED, InvestigationStatus.RUNNING)


async def active_investigation(
    session: AsyncSession, incident_id: uuid.UUID
) -> Investigation | None:
    found: Investigation | None = await session.scalar(
        select(Investigation).where(
            Investigation.incident_id == incident_id, Investigation.status.in_(ACTIVE)
        )
    )
    return found


async def enqueue(
    session: AsyncSession, incident: Incident, requested_by: str
) -> tuple[Investigation, bool]:
    """The active investigation of the incident, creating one if needed. Caller commits."""
    if existing := await active_investigation(session, incident.id):
        return existing, False
    investigation = Investigation(
        organization_id=incident.organization_id, incident_id=incident.id, requested_by=requested_by
    )
    try:
        async with session.begin_nested():
            session.add(investigation)
    except IntegrityError:
        found = await active_investigation(session, incident.id)
        if found is None:
            raise
        return found, False
    # Published as incident.investigation.requested.v1.
    user = requested_by.removeprefix("user:")
    actor = (
        Actor(ActorType.USER, user, incident.organization_id)
        if user != requested_by
        else Actor(ActorType.SYSTEM, requested_by, incident.organization_id)
    )
    await note(
        session,
        incident,
        actor,
        event_type="incident.investigation_requested",
        title="Investigation requested",
        metadata={"investigation_id": str(investigation.id)},
    )
    return investigation, True


async def claim(
    sessions: async_sessionmaker[AsyncSession],
    lease: timedelta,
    *,
    only: uuid.UUID | None = None,
) -> Investigation | None:
    """Take the oldest runnable investigation and lease it to this worker."""
    now = datetime.now(UTC)
    async with sessions() as session:
        statement = (
            select(Investigation)
            .where(
                or_(
                    Investigation.status == InvestigationStatus.QUEUED,
                    (Investigation.status == InvestigationStatus.RUNNING)
                    & (Investigation.lease_until < now),
                )
            )
            .order_by(Investigation.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if only is not None:
            statement = statement.where(Investigation.id == only)
        investigation = await session.scalar(statement)
        if investigation is None:
            return None
        investigation.attempts += 1
        if investigation.attempts > MAX_ATTEMPTS:
            investigation.status = InvestigationStatus.FAILED
            investigation.error = f"gave up after {MAX_ATTEMPTS} attempts"
            investigation.completed_at = now
            await session.commit()
            return None
        investigation.status = InvestigationStatus.RUNNING
        investigation.lease_until = now + lease
        investigation.started_at = investigation.started_at or now
        await session.commit()
        return investigation
