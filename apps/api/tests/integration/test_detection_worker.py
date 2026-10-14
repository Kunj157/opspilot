"""The detection worker: fake Prometheus, real PostgreSQL."""

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
    DetectorCheckpoint,
    HealthStatus,
    Incident,
    IncidentEvent,
    Organization,
    Service,
    ServiceDependency,
)
from opspilot_api.detection.rules import ErrorRateRule
from opspilot_api.detection.worker import DetectionWorker
from opspilot_api.telemetry import Sample, Series, TelemetryUnavailable

pytestmark = pytest.mark.integration

RULE = ErrorRateRule(trigger_windows=3, recovery_windows=2, cooldown_windows=2)


class FakePrometheus:
    """Answers the worker's two queries from per-(namespace, service) rates."""

    def __init__(self) -> None:
        self.rates: dict[tuple[str, str], tuple[float, float]] = {}
        self.down = False
        self.queries: list[str] = []

    async def query(self, promql: str, at: datetime) -> list[Sample]:
        self.queries.append(promql)
        if self.down:
            raise TelemetryUnavailable("prometheus unreachable: ConnectError")
        index = 1 if "http_errors_total" in promql else 0
        return [
            Sample({"namespace": ns, "service": svc}, rates[index])
            for (ns, svc), rates in self.rates.items()
            if not (index == 1 and rates[1] == 0)  # no error series until the first error
        ]

    async def query_range(
        self, promql: str, start: datetime, end: datetime, step: timedelta
    ) -> list[Series]:
        raise NotImplementedError


@pytest.fixture
async def engine(migrated_database_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(migrated_database_url)
    yield eng
    await eng.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def namespace(sessions: async_sessionmaker[AsyncSession]) -> str:
    """A fresh namespace with checkout (watched) and an unwatched catalog entry."""
    ns = f"demo-{uuid.uuid4().hex[:8]}"
    async with sessions() as session:
        org = Organization(name="Acme", slug=f"org-{uuid.uuid4().hex[:10]}")
        session.add(org)
        await session.flush()
        session.add_all(
            [
                Service(
                    organization_id=org.id,
                    name="Checkout",
                    slug="checkout",
                    namespace=ns,
                    deployment_name="checkout",
                ),
                Service(organization_id=org.id, name="Billing", slug="billing"),
            ]
        )
        await session.commit()
    return ns


def worker(
    sessions: async_sessionmaker[AsyncSession], prometheus: FakePrometheus
) -> DetectionWorker:
    return DetectionWorker(sessions, prometheus, rule=RULE, lag=timedelta(seconds=30))


async def incidents_for(sessions: async_sessionmaker[AsyncSession], ns: str) -> list[Incident]:
    async with sessions() as session:
        rows = await session.scalars(
            sa.select(Incident)
            .join(Service, Service.id == Incident.service_id)
            .where(Service.namespace == ns)
        )
        return list(rows)


async def checkout(sessions: async_sessionmaker[AsyncSession], ns: str) -> Service:
    async with sessions() as session:
        return await session.scalar(
            sa.select(Service).where(Service.namespace == ns)
        ) or pytest.fail("checkout not seeded")


async def test_a_sustained_error_rate_opens_exactly_one_incident(
    sessions: async_sessionmaker[AsyncSession], namespace: str
) -> None:
    prometheus = FakePrometheus()
    prometheus.rates[(namespace, "checkout")] = (5.0, 2.0)
    detection = worker(sessions, prometheus)

    for _ in range(6):
        await detection.cycle(datetime.now(UTC))

    found = await incidents_for(sessions, namespace)
    assert len(found) == 1
    assert found[0].source == "detector"
    assert (await checkout(sessions, namespace)).health_status is HealthStatus.CRITICAL


async def test_healthy_traffic_and_unwatched_services_open_nothing(
    sessions: async_sessionmaker[AsyncSession], namespace: str
) -> None:
    prometheus = FakePrometheus()
    prometheus.rates[(namespace, "checkout")] = (5.0, 0.0)
    detection = worker(sessions, prometheus)

    for _ in range(6):
        await detection.cycle(datetime.now(UTC))

    assert await incidents_for(sessions, namespace) == []
    assert (await checkout(sessions, namespace)).health_status is HealthStatus.HEALTHY


async def test_a_prometheus_outage_changes_nothing(
    sessions: async_sessionmaker[AsyncSession], namespace: str
) -> None:
    prometheus = FakePrometheus()
    prometheus.rates[(namespace, "checkout")] = (5.0, 2.0)
    detection = worker(sessions, prometheus)
    await detection.cycle(datetime.now(UTC))
    await detection.cycle(datetime.now(UTC))

    prometheus.down = True
    outcome = await detection.cycle(datetime.now(UTC))

    assert outcome == "telemetry_unavailable"
    assert await incidents_for(sessions, namespace) == []
    prometheus.down = False
    await detection.cycle(datetime.now(UTC))
    assert len(await incidents_for(sessions, namespace)) == 1


async def test_a_restarted_worker_does_not_open_a_second_incident(
    sessions: async_sessionmaker[AsyncSession], namespace: str
) -> None:
    prometheus = FakePrometheus()
    prometheus.rates[(namespace, "checkout")] = (5.0, 2.0)
    for _ in range(3):
        await worker(sessions, prometheus).cycle(datetime.now(UTC))

    restarted = worker(sessions, prometheus)
    for _ in range(3):
        await restarted.cycle(datetime.now(UTC))

    assert len(await incidents_for(sessions, namespace)) == 1
    async with sessions() as session:
        service = await checkout(sessions, namespace)
        state = await session.get_one(DetectorCheckpoint, (service.id, RULE.name))
        assert state.state["active"] is True


async def test_recovery_is_noted_on_the_incident(
    sessions: async_sessionmaker[AsyncSession], namespace: str
) -> None:
    prometheus = FakePrometheus()
    prometheus.rates[(namespace, "checkout")] = (5.0, 2.0)
    detection = worker(sessions, prometheus)
    for _ in range(3):
        await detection.cycle(datetime.now(UTC))

    prometheus.rates[(namespace, "checkout")] = (5.0, 0.0)
    for _ in range(2):
        await detection.cycle(datetime.now(UTC))

    [incident] = await incidents_for(sessions, namespace)
    async with sessions() as session:
        types = list(
            await session.scalars(
                sa.select(IncidentEvent.event_type).where(IncidentEvent.incident_id == incident.id)
            )
        )
    assert "incident.signal_recovered" in types
    assert (await checkout(sessions, namespace)).health_status is HealthStatus.HEALTHY


async def test_missing_metrics_neither_open_nor_recover(
    sessions: async_sessionmaker[AsyncSession], namespace: str
) -> None:
    detection = worker(sessions, FakePrometheus())

    for _ in range(6):
        await detection.cycle(datetime.now(UTC))

    assert await incidents_for(sessions, namespace) == []
    assert (await checkout(sessions, namespace)).health_status is HealthStatus.UNKNOWN


async def test_a_failing_dependency_gets_the_incident_and_callers_add_impact(
    sessions: async_sessionmaker[AsyncSession], namespace: str
) -> None:
    async with sessions() as session:
        checkout_svc = await session.scalar(
            sa.select(Service).where(Service.namespace == namespace)
        )
        assert checkout_svc is not None
        storefront = Service(
            organization_id=checkout_svc.organization_id,
            name="Storefront",
            slug="storefront",
            namespace=namespace,
            deployment_name="storefront",
        )
        session.add(storefront)
        await session.flush()
        session.add(
            ServiceDependency(
                organization_id=checkout_svc.organization_id,
                source_service_id=storefront.id,
                target_service_id=checkout_svc.id,
            )
        )
        await session.commit()
    prometheus = FakePrometheus()
    prometheus.rates[(namespace, "checkout")] = (2.0, 1.0)
    prometheus.rates[(namespace, "storefront")] = (5.0, 1.0)
    detection = worker(sessions, prometheus)

    for _ in range(5):
        await detection.cycle(datetime.now(UTC))

    [incident] = await incidents_for(sessions, namespace)
    assert incident.service_id == checkout_svc.id
    async with sessions() as session:
        notes = list(
            await session.scalars(
                sa.select(IncidentEvent.title).where(
                    IncidentEvent.incident_id == incident.id,
                    IncidentEvent.event_type == "incident.impact_detected",
                )
            )
        )
        caller = await session.get_one(Service, storefront.id)
    assert notes == ["Storefront is also affected"]
    assert caller.health_status is HealthStatus.DEGRADED
