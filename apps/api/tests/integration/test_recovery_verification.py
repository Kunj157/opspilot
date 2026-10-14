"""Recovery verification: rollout, verification window, baseline, and the incident's next state."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from opspilot_api.db.models import (
    AuditLog,
    ExecutionStatus,
    Incident,
    IncidentEvent,
    IncidentStatus,
    Investigation,
    Organization,
    ProposalStatus,
    RemediationAction,
    RemediationExecution,
    RemediationProposal,
    Severity,
)
from opspilot_api.kube import ConfigMapInfo, Revision, RolloutStatus
from opspilot_api.remediation.verification import pending, verify
from opspilot_api.telemetry import Sample, Series, TelemetryUnavailable

pytestmark = pytest.mark.integration
STARTED = datetime.now(UTC) - timedelta(minutes=20)
EXECUTED = datetime.now(UTC) - timedelta(minutes=1)


class Metrics:
    """Requests and errors over a window; the baseline window ends before the incident."""

    def __init__(
        self,
        *,
        error_rate: float = 0.0,
        p95: float = 0.05,
        baseline_p95: float = 0.05,
        down: bool = False,
    ) -> None:
        self.error_rate, self.p95, self.baseline_p95, self.down = (
            error_rate,
            p95,
            baseline_p95,
            down,
        )
        self.queries: list[tuple[str, datetime]] = []

    async def query(self, promql: str, at: datetime) -> list[Sample]:
        if self.down:
            raise TelemetryUnavailable("prometheus unreachable")
        self.queries.append((promql, at))
        baseline = at < STARTED
        if "http_errors_total" in promql:
            return [Sample({}, 0.0 if baseline else 600 * self.error_rate)]
        if "duration" in promql:
            return [Sample({}, self.baseline_p95 if baseline else self.p95)]
        return [Sample({}, 600.0)]

    async def query_range(
        self, promql: str, start: datetime, end: datetime, step: timedelta
    ) -> list[Series]:
        return []


class Kube:
    def __init__(self, status: RolloutStatus | None = None) -> None:
        self.status = status or RolloutStatus(2, 2, 2, 2, True, ["Available=True"])

    async def rollout_history(self, namespace: str, deployment: str) -> list[Revision]:
        return []

    async def rollout_status(self, namespace: str, deployment: str) -> RolloutStatus:
        return self.status

    async def config_maps(self, namespace: str, names: list[str]) -> list[ConfigMapInfo]:
        return []


@pytest.fixture
async def sessions(migrated_database_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_database_url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def executed(sessions: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    """An incident in VERIFYING after a successful rollback; returns the execution ID."""
    async with sessions() as session:
        org = Organization(name="Acme", slug=f"org-{uuid.uuid4().hex[:10]}")
        session.add(org)
        await session.flush()
        incident = Incident(
            organization_id=org.id,
            title="High error rate on Checkout",
            severity=Severity.CRITICAL,
            source="detector",
            status=IncidentStatus.VERIFYING,
            started_at=STARTED,
        )
        session.add(incident)
        await session.flush()
        proposal = RemediationProposal(
            organization_id=org.id,
            incident_id=incident.id,
            action_type=RemediationAction.ROLLBACK_DEPLOYMENT,
            description="Roll back checkout",
            parameters={"namespace": "demo", "deployment": "checkout", "to_revision": 6},
            risk_level="medium",
            verification_plan={"window_minutes": 3, "max_error_rate": 0.02},
            status=ProposalStatus.EXECUTED,
        )
        session.add(proposal)
        await session.flush()
        execution = RemediationExecution(
            organization_id=org.id,
            proposal_id=proposal.id,
            incident_id=incident.id,
            idempotency_key=f"{proposal.id}:v1",
            status=ExecutionStatus.SUCCEEDED,
            completed_at=EXECUTED,
            verification_status="pending",
        )
        session.add(execution)
        await session.commit()
        return execution.id


async def snapshot(
    sessions: async_sessionmaker[AsyncSession], execution_id: uuid.UUID
) -> tuple[RemediationExecution, Incident, list[str], list[str], list[Investigation]]:
    async with sessions() as session:
        execution = await session.get_one(RemediationExecution, execution_id)
        incident = await session.get_one(Incident, execution.incident_id)
        events = list(
            await session.scalars(
                sa.select(IncidentEvent.event_type)
                .where(IncidentEvent.incident_id == incident.id)
                .order_by(IncidentEvent.sequence)
            )
        )
        audit = list(
            await session.scalars(
                sa.select(AuditLog.action).where(AuditLog.resource_id == str(execution.proposal_id))
            )
        )
        investigations = list(
            await session.scalars(
                sa.select(Investigation).where(Investigation.incident_id == incident.id)
            )
        )
        return execution, incident, events, audit, investigations


async def run_to_verdict(
    sessions: async_sessionmaker[AsyncSession],
    execution_id: uuid.UUID,
    kube: Kube,
    metrics: Metrics,
) -> None:
    """Rollout check now, then the window check once the window has passed."""
    now = datetime.now(UTC)
    assert await verify(sessions, kube, metrics, execution_id, now=now) is None
    assert (
        await verify(sessions, kube, metrics, execution_id, now=now + timedelta(minutes=1)) is None
    )
    await verify(sessions, kube, metrics, execution_id, now=now + timedelta(minutes=3, seconds=5))


async def test_a_recovered_service_resolves_the_incident(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    execution_id = await executed(sessions)
    metrics = Metrics(error_rate=0.004, p95=0.06)

    assert execution_id in await pending(sessions)
    await run_to_verdict(sessions, execution_id, Kube(), metrics)

    execution, incident, events, audit, _ = await snapshot(sessions, execution_id)
    assert execution.verification_status == "passed"
    assert execution.verification["window"]["error_rate"] == pytest.approx(0.004)
    assert execution.verification["rollout"]["complete"] is True
    assert execution.rollout_completed_at is not None
    assert incident.status is IncidentStatus.RESOLVED
    assert "incident.verification_passed" in events
    assert "remediation.verified" in audit
    assert execution_id not in await pending(sessions)
    # Measured over the 3 minutes after the rollout, and before the incident for the baseline.
    window_query = next(q for q, _ in metrics.queries if "http_errors_total" in q)
    assert "[3m]" in window_query
    assert any(at < STARTED for _, at in metrics.queries)


async def test_nothing_is_decided_before_the_window_has_passed(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    execution_id = await executed(sessions)
    now = datetime.now(UTC)

    for minutes in (0, 1, 2):
        assert (
            await verify(
                sessions, Kube(), Metrics(), execution_id, now=now + timedelta(minutes=minutes)
            )
            is None
        )

    execution, incident, *_ = await snapshot(sessions, execution_id)
    assert execution.verification_status == "pending"
    assert incident.status is IncidentStatus.VERIFYING


async def test_a_lasting_error_rate_reopens_the_investigation(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    execution_id = await executed(sessions)

    await run_to_verdict(sessions, execution_id, Kube(), Metrics(error_rate=0.3))

    execution, incident, events, audit, investigations = await snapshot(sessions, execution_id)
    assert execution.verification_status == "failed"
    assert "30.0%" in execution.verification["reason"]
    assert incident.status is IncidentStatus.INVESTIGATING
    assert "incident.verification_failed" in events
    assert "remediation.verification_failed" in audit
    assert len(investigations) == 1


async def test_latency_far_above_the_baseline_fails(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    execution_id = await executed(sessions)

    await run_to_verdict(sessions, execution_id, Kube(), Metrics(p95=0.4, baseline_p95=0.05))

    execution, incident, *_ = await snapshot(sessions, execution_id)
    assert execution.verification_status == "failed"
    assert "baseline" in execution.verification["reason"]
    assert incident.status is IncidentStatus.INVESTIGATING


async def test_a_stalled_rollout_fails_immediately(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    execution_id = await executed(sessions)
    stalled = Kube(
        RolloutStatus(2, 1, 1, 1, False, ["Progressing=False (ProgressDeadlineExceeded)"])
    )

    await verify(sessions, stalled, Metrics(), execution_id)

    execution, incident, *_ = await snapshot(sessions, execution_id)
    assert execution.verification_status == "failed"
    assert execution.verification["reason"] == "the rollout stalled"
    assert incident.status is IncidentStatus.INVESTIGATING


async def test_a_rollout_that_never_completes_times_out(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    execution_id = await executed(sessions)
    slow = Kube(RolloutStatus(2, 1, 1, 1, False, ["Progressing=True"]))

    assert await verify(sessions, slow, Metrics(), execution_id) is None
    later = datetime.now(UTC) + timedelta(minutes=6)
    verdict = await verify(sessions, slow, Metrics(), execution_id, now=later)

    assert verdict is not None
    assert verdict.passed is False
    assert "did not complete" in verdict.reason


async def test_unavailable_telemetry_waits_then_fails_safe(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    execution_id = await executed(sessions)
    down = Metrics(down=True)
    now = datetime.now(UTC)
    await verify(sessions, Kube(), down, execution_id, now=now)

    assert (
        await verify(sessions, Kube(), down, execution_id, now=now + timedelta(minutes=4)) is None
    )
    verdict = await verify(sessions, Kube(), down, execution_id, now=now + timedelta(minutes=9))

    assert verdict is not None
    assert "manual review" in verdict.reason
    _, incident, *_ = await snapshot(sessions, execution_id)
    assert incident.status is IncidentStatus.INVESTIGATING
