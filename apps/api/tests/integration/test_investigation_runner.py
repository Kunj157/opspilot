"""Worker loop: detector incidents are investigated automatically; crashes are retried."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from prometheus_client import REGISTRY
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from opspilot_api.agents.investigation import Investigator
from opspilot_api.agents.llm import ScriptedLLM
from opspilot_api.agents.runner import InvestigationRunner, context_factory
from opspilot_api.db.models import (
    Incident,
    IncidentStatus,
    Investigation,
    InvestigationStatus,
    Organization,
    RemediationProposal,
    Service,
)
from opspilot_api.detection.rules import ErrorRateRule
from opspilot_api.detection.worker import DetectionWorker
from tests.integration.test_detection_worker import FakePrometheus
from tests.integration.test_investigation import Kube, Logs, Metrics, Traces, happy_model

pytestmark = pytest.mark.integration


@pytest.fixture
async def engine(migrated_database_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(migrated_database_url)
    yield eng
    await eng.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def runner(sessions: async_sessionmaker[AsyncSession], model: object) -> InvestigationRunner:
    make = context_factory(
        sessions,
        metrics=Metrics(),
        logs=Logs(),
        traces=Traces(),
        kube=Kube(),
        embedder=None,
        allowed_namespaces=frozenset({"demo"}),
    )
    return InvestigationRunner(sessions, lambda: Investigator(sessions, ScriptedLLM(model), make))  # type: ignore[arg-type]


async def drain(r: InvestigationRunner) -> None:
    """Run claimable investigations until the queue (for this test) is empty."""
    for _ in range(20):
        if not await r.run_once():
            return


async def test_a_detector_incident_is_investigated_end_to_end(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    namespace = "demo"
    async with sessions() as session:
        org = Organization(name="Acme", slug=f"org-{uuid.uuid4().hex[:10]}")
        session.add(org)
        await session.flush()
        session.add(
            Service(
                organization_id=org.id,
                name="Checkout",
                slug="checkout",
                namespace=namespace,
                deployment_name=f"checkout-{uuid.uuid4().hex[:6]}",
            )
        )
        await session.commit()
        checkout = await session.scalar(sa.select(Service).where(Service.organization_id == org.id))
    assert checkout is not None
    prometheus = FakePrometheus()
    prometheus.rates[(namespace, checkout.deployment_name or "")] = (5.0, 2.0)
    detection = DetectionWorker(
        sessions,
        prometheus,
        rule=ErrorRateRule(trigger_windows=2),
        lag=timedelta(seconds=30),
        auto_investigate=True,
    )
    for _ in range(3):
        await detection.cycle(datetime.now(UTC))

    await drain(runner(sessions, happy_model()))

    async with sessions() as session:
        incident = await session.scalar(
            sa.select(Incident).where(Incident.service_id == checkout.id)
        )
        assert incident is not None
        investigations = list(
            await session.scalars(
                sa.select(Investigation).where(Investigation.incident_id == incident.id)
            )
        )
        proposals = list(
            await session.scalars(
                sa.select(RemediationProposal).where(RemediationProposal.incident_id == incident.id)
            )
        )
    assert [i.status for i in investigations] == [InvestigationStatus.COMPLETED]
    assert investigations[0].requested_by == "detector:error-rate"
    assert len(proposals) == 1
    assert incident.status is IncidentStatus.AWAITING_APPROVAL


async def test_a_crashed_investigation_is_retried_after_its_lease(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    from tests.integration.test_investigation import setup

    investigation_id = await setup(sessions)
    calls = {"n": 0}
    model = happy_model()

    def flaky(schema: object, prompt: str) -> dict[str, object]:
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("worker died mid-run")
        return model(schema, prompt)  # type: ignore[arg-type]

    def runs(outcome: str) -> float:
        labels = {"agent": "investigation", "outcome": outcome}
        return REGISTRY.get_sample_value("opspilot_agent_runs_total", labels) or 0

    crashed, completed = runs("crashed"), runs("completed")
    r = runner(sessions, flaky)
    await r.run_once()
    async with sessions() as session:
        inv = await session.get_one(Investigation, investigation_id)
        assert inv.status is InvestigationStatus.RUNNING
        await session.execute(
            sa.update(Investigation)
            .where(Investigation.id == investigation_id)
            .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
        await session.commit()

    await drain(r)

    async with sessions() as session:
        inv = await session.get_one(Investigation, investigation_id)
    assert inv.status is InvestigationStatus.COMPLETED
    assert inv.attempts == 2
    assert runs("crashed") == crashed + 1
    assert runs("completed") == completed + 1
