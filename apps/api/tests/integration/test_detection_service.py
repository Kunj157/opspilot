"""Detector decisions → incidents, timeline events, service health, and records."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from opspilot_api.db.models import (
    AnomalyDetection,
    HealthStatus,
    Incident,
    IncidentEvent,
    IncidentStatus,
    Organization,
    Service,
    Severity,
)
from opspilot_api.detection.rules import Decision, ErrorRateRule, Outcome
from opspilot_api.detection.service import apply_decision

pytestmark = pytest.mark.integration

RULE = ErrorRateRule()
END = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
START = END - timedelta(minutes=1)


def decision(outcome: Outcome, error_rate: float = 0.4) -> Decision:
    return Decision(
        outcome,
        score=error_rate / RULE.threshold,
        threshold=RULE.threshold,
        features={"error_rate": error_rate, "requests_per_second": 5.0},
    )


@pytest.fixture
async def engine(migrated_database_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(migrated_database_url)
    yield eng
    await eng.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def service(sessions: async_sessionmaker[AsyncSession]) -> Service:
    async with sessions() as session:
        org = Organization(name="Acme", slug=f"org-{uuid.uuid4().hex[:10]}")
        session.add(org)
        await session.flush()
        svc = Service(organization_id=org.id, name="Checkout", slug="checkout", namespace="demo")
        session.add(svc)
        await session.commit()
        return svc


async def apply(
    sessions: async_sessionmaker[AsyncSession],
    service: Service,
    outcome: Outcome,
    rate: float = 0.4,
) -> Incident | None:
    async with sessions() as session:
        svc = await session.get_one(Service, service.id)
        incident = await apply_decision(
            session, svc, RULE, decision(outcome, rate), window_start=START, window_end=END
        )
        await session.commit()
        return incident


async def open_incidents(
    sessions: async_sessionmaker[AsyncSession], service: Service
) -> list[Incident]:
    async with sessions() as session:
        rows = await session.scalars(
            sa.select(Incident).where(
                Incident.service_id == service.id, Incident.status != IncidentStatus.RESOLVED
            )
        )
        return list(rows)


async def timeline(sessions: async_sessionmaker[AsyncSession], incident: Incident) -> list[str]:
    async with sessions() as session:
        rows = await session.scalars(
            sa.select(IncidentEvent.event_type)
            .where(IncidentEvent.incident_id == incident.id)
            .order_by(IncidentEvent.sequence)
        )
        return list(rows)


async def test_a_trigger_opens_a_detector_incident(
    sessions: async_sessionmaker[AsyncSession], service: Service
) -> None:
    incident = await apply(sessions, service, Outcome.TRIGGERED, rate=0.4)

    assert incident is not None
    assert (incident.source, incident.severity, incident.status) == (
        "detector",
        Severity.CRITICAL,
        IncidentStatus.DETECTED,
    )
    assert incident.title == "High error rate on Checkout"
    assert incident.detection_score == pytest.approx(8.0)
    assert incident.dedup_key == f"{service.id}:error-rate:high_error_rate"
    async with sessions() as session:
        anomaly = await session.scalar(
            sa.select(IncidentEvent).where(
                IncidentEvent.incident_id == incident.id,
                IncidentEvent.event_type == "incident.anomaly_detected",
            )
        )
    assert anomaly is not None
    assert anomaly.metadata_json["detector"] == "error-rate"
    assert anomaly.metadata_json["service_id"] == str(service.id)
    async with sessions() as session:
        svc = await session.get_one(Service, service.id)
        assert svc.health_status is HealthStatus.CRITICAL


@pytest.mark.parametrize(("rate", "severity"), [(0.06, Severity.MEDIUM), (0.12, Severity.HIGH)])
async def test_severity_follows_the_score(
    sessions: async_sessionmaker[AsyncSession], service: Service, rate: float, severity: Severity
) -> None:
    incident = await apply(sessions, service, Outcome.TRIGGERED, rate=rate)

    assert incident is not None
    assert incident.severity is severity


async def test_ongoing_breaches_reuse_the_open_incident_quietly(
    sessions: async_sessionmaker[AsyncSession], service: Service
) -> None:
    first = await apply(sessions, service, Outcome.TRIGGERED)
    again = await apply(sessions, service, Outcome.ONGOING)
    assert first is not None
    assert again is not None

    assert again.id == first.id
    assert again.version == first.version
    assert len(await open_incidents(sessions, service)) == 1
    assert await timeline(sessions, first) == ["incident.created", "incident.anomaly_detected"]


async def test_concurrent_triggers_create_exactly_one_incident(
    sessions: async_sessionmaker[AsyncSession], service: Service
) -> None:
    results = await asyncio.gather(*[apply(sessions, service, Outcome.TRIGGERED) for _ in range(5)])

    assert len({r.id for r in results if r}) == 1
    assert len(await open_incidents(sessions, service)) == 1


async def test_recovery_notes_the_incident_and_restores_health(
    sessions: async_sessionmaker[AsyncSession], service: Service
) -> None:
    incident = await apply(sessions, service, Outcome.TRIGGERED)
    assert incident is not None

    await apply(sessions, service, Outcome.RECOVERED, rate=0.0)

    assert await timeline(sessions, incident) == [
        "incident.created",
        "incident.anomaly_detected",
        "incident.signal_recovered",
    ]
    async with sessions() as session:
        svc = await session.get_one(Service, service.id)
        assert svc.health_status is HealthStatus.HEALTHY
        still_open = await session.get_one(Incident, incident.id)
        assert still_open.status is IncidentStatus.DETECTED


async def test_a_breach_after_resolution_opens_a_new_incident(
    sessions: async_sessionmaker[AsyncSession], service: Service
) -> None:
    first = await apply(sessions, service, Outcome.TRIGGERED)
    assert first is not None
    async with sessions() as session:
        await session.execute(
            sa.update(Incident)
            .where(Incident.id == first.id)
            .values(status=IncidentStatus.RESOLVED)
        )
        await session.commit()

    second = await apply(sessions, service, Outcome.ONGOING)

    assert second is not None
    assert second.id != first.id


async def test_every_decision_is_recorded(
    sessions: async_sessionmaker[AsyncSession], service: Service
) -> None:
    incident = await apply(sessions, service, Outcome.TRIGGERED)
    await apply(sessions, service, Outcome.ONGOING)
    await apply(sessions, service, Outcome.RECOVERED, rate=0.0)

    async with sessions() as session:
        rows = (
            await session.scalars(
                sa.select(AnomalyDetection)
                .where(AnomalyDetection.service_id == service.id)
                .order_by(AnomalyDetection.created_at)
            )
        ).all()
    assert [r.outcome for r in rows] == ["triggered", "ongoing", "recovered"]
    assert incident is not None
    assert {r.incident_id for r in rows} == {incident.id}
    assert rows[0].features == {"error_rate": 0.4, "requests_per_second": 5.0}
    assert (rows[0].detector, rows[0].model_version, rows[0].window_end) == (
        "error-rate",
        "rule-v1",
        END,
    )


async def test_recovery_without_an_open_incident_only_records(
    sessions: async_sessionmaker[AsyncSession], service: Service
) -> None:
    assert await apply(sessions, service, Outcome.RECOVERED, rate=0.0) is None
