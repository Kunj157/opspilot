"""The incident domain service against a real database."""

import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from opspilot_api.db.models import (
    ActorType,
    AuditLog,
    Incident,
    IncidentEvent,
    IncidentStatus,
    Organization,
    Severity,
)
from opspilot_api.incidents.service import (
    Actor,
    IncidentConflictError,
    InvalidTransitionError,
    acknowledge,
    create_incident,
    transition,
    update_details,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def engine(migrated_database_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(migrated_database_url)
    yield eng
    await eng.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def actor(sessions: async_sessionmaker[AsyncSession]) -> Actor:
    async with sessions() as session:
        org = Organization(name="Acme", slug=f"org-{uuid.uuid4().hex[:10]}")
        session.add(org)
        await session.commit()
        return Actor(type=ActorType.USER, id="user-1", organization_id=org.id)


async def new_incident(sessions: async_sessionmaker[AsyncSession], actor: Actor) -> Incident:
    async with sessions() as session:
        incident = await create_incident(
            session, actor, title="Checkout errors", severity=Severity.HIGH, source="manual"
        )
        await session.commit()
        return incident


async def events(session: AsyncSession, incident_id: uuid.UUID) -> list[IncidentEvent]:
    rows = await session.execute(
        sa.select(IncidentEvent)
        .where(IncidentEvent.incident_id == incident_id)
        .order_by(IncidentEvent.sequence)
    )
    return list(rows.scalars())


async def audit_actions(session: AsyncSession, incident_id: uuid.UUID) -> list[str]:
    rows = await session.execute(
        sa.select(AuditLog.action)
        .where(AuditLog.resource_id == str(incident_id))
        .order_by(AuditLog.created_at, AuditLog.id)
    )
    return list(rows.scalars())


async def test_create_starts_detected_with_an_event_and_audit_record(
    sessions: async_sessionmaker[AsyncSession], actor: Actor
) -> None:
    incident = await new_incident(sessions, actor)

    async with sessions() as session:
        stored = await session.get(Incident, incident.id)
        assert stored is not None
        assert stored.status is IncidentStatus.DETECTED
        assert stored.version == 1
        assert [e.event_type for e in await events(session, incident.id)] == ["incident.created"]
        assert await audit_actions(session, incident.id) == ["incident.created"]


async def test_valid_transition_bumps_version_and_records_both_trails(
    sessions: async_sessionmaker[AsyncSession], actor: Actor
) -> None:
    incident = await new_incident(sessions, actor)

    async with sessions() as session:
        loaded = await session.get(Incident, incident.id)
        assert loaded is not None
        await transition(
            session, loaded, IncidentStatus.INVESTIGATING, expected_version=1, actor=actor
        )
        await session.commit()

    async with sessions() as session:
        stored = await session.get(Incident, incident.id)
        assert stored is not None
        assert (stored.status, stored.version) == (IncidentStatus.INVESTIGATING, 2)
        trail = await events(session, incident.id)
        assert [e.event_type for e in trail] == ["incident.created", "incident.status_changed"]
        assert trail[1].metadata_json == {"from": "DETECTED", "to": "INVESTIGATING"}
        assert await audit_actions(session, incident.id) == [
            "incident.created",
            "incident.status_changed",
        ]


async def test_invalid_transition_is_rejected_and_writes_nothing(
    sessions: async_sessionmaker[AsyncSession], actor: Actor
) -> None:
    incident = await new_incident(sessions, actor)

    async with sessions() as session:
        loaded = await session.get(Incident, incident.id)
        assert loaded is not None
        with pytest.raises(InvalidTransitionError):
            await transition(
                session, loaded, IncidentStatus.RESOLVED, expected_version=1, actor=actor
            )
        await session.rollback()

    async with sessions() as session:
        stored = await session.get(Incident, incident.id)
        assert stored is not None
        assert (stored.status, stored.version) == (IncidentStatus.DETECTED, 1)
        assert len(await events(session, incident.id)) == 1


async def test_stale_version_is_a_conflict(
    sessions: async_sessionmaker[AsyncSession], actor: Actor
) -> None:
    incident = await new_incident(sessions, actor)

    async with sessions() as session:
        loaded = await session.get(Incident, incident.id)
        assert loaded is not None
        with pytest.raises(IncidentConflictError):
            await transition(
                session, loaded, IncidentStatus.INVESTIGATING, expected_version=7, actor=actor
            )


async def test_concurrent_transitions_cannot_both_win(
    sessions: async_sessionmaker[AsyncSession], actor: Actor
) -> None:
    incident = await new_incident(sessions, actor)

    async def attempt() -> str:
        async with sessions() as session:
            loaded = await session.get(Incident, incident.id)
            assert loaded is not None
            await asyncio.sleep(0.05)  # both read version 1 before either writes
            try:
                await transition(
                    session, loaded, IncidentStatus.INVESTIGATING, expected_version=1, actor=actor
                )
                await session.commit()
                return "won"
            except IncidentConflictError:
                await session.rollback()
                return "conflict"

    results = sorted(await asyncio.gather(attempt(), attempt()))

    assert results == ["conflict", "won"]
    async with sessions() as session:
        stored = await session.get(Incident, incident.id)
        assert stored is not None
        assert stored.version == 2
        assert len(await events(session, incident.id)) == 2


async def test_resolving_sets_resolved_at(
    sessions: async_sessionmaker[AsyncSession], actor: Actor
) -> None:
    incident = await new_incident(sessions, actor)
    path = [IncidentStatus.INVESTIGATING, IncidentStatus.MONITORING, IncidentStatus.RESOLVED]

    async with sessions() as session:
        loaded = await session.get(Incident, incident.id)
        assert loaded is not None
        for version, target in enumerate(path, start=1):
            await transition(session, loaded, target, expected_version=version, actor=actor)
        await session.commit()
        assert loaded.resolved_at is not None
        assert loaded.version == 4


async def test_acknowledge_records_time_and_assignee_once(
    sessions: async_sessionmaker[AsyncSession], actor: Actor
) -> None:
    incident = await new_incident(sessions, actor)
    assignee = uuid.uuid4()

    async with sessions() as session:
        loaded = await session.get(Incident, incident.id)
        assert loaded is not None
        await acknowledge(session, loaded, expected_version=1, actor=actor, assignee_id=None)
        await session.commit()
        first_ack = loaded.acknowledged_at
        with pytest.raises(InvalidTransitionError):
            await acknowledge(
                session, loaded, expected_version=2, actor=actor, assignee_id=assignee
            )

    assert first_ack is not None


async def test_detail_update_is_versioned_and_recorded(
    sessions: async_sessionmaker[AsyncSession], actor: Actor
) -> None:
    incident = await new_incident(sessions, actor)

    async with sessions() as session:
        loaded = await session.get(Incident, incident.id)
        assert loaded is not None
        await update_details(
            session,
            loaded,
            expected_version=1,
            actor=actor,
            changes={"severity": Severity.CRITICAL},
        )
        await session.commit()
        trail = await events(session, incident.id)

    assert loaded.version == 2
    assert trail[-1].event_type == "incident.updated"
    assert trail[-1].metadata_json == {"changed": ["severity"]}
