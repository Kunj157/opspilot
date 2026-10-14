"""Executing approved proposals: exactly once, re-validated, audited, and reopened on failure."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from prometheus_client import REGISTRY
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from opspilot_api.db.models import (
    Approval,
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
    User,
)
from opspilot_api.kube import RemediationFailed, check_namespace
from opspilot_api.remediation.executor import claim, execute
from opspilot_api.routes.investigations import proposals_out

pytestmark = pytest.mark.integration
ALLOWED = frozenset({"demo"})


class FakeWriter:
    def __init__(self, fail: Exception | None = None, fail_times: int = 1) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.fail = fail
        self.fail_times = fail_times

    async def _call(self, *call: Any) -> None:
        await asyncio.sleep(0.01)
        self.calls.append(call)
        if self.fail and self.fail_times > 0:
            self.fail_times -= 1
            raise self.fail

    async def rollback_deployment(
        self, namespace: str, deployment: str, to_revision: int, *, cause: str
    ) -> dict[str, Any]:
        check_namespace(namespace, ALLOWED)
        await self._call("rollback", namespace, deployment, to_revision)
        return {"rolled_back_to": to_revision, "version": "1.0.0"}

    async def restart_deployment(
        self, namespace: str, deployment: str, *, restarted_at: str
    ) -> dict[str, Any]:
        await self._call("restart", namespace, deployment, restarted_at)
        return {"restarted_at": restarted_at}

    async def scale_deployment_within_bounds(
        self, namespace: str, deployment: str, replicas: int, *, maximum: int
    ) -> dict[str, Any]:
        await self._call("scale", namespace, deployment, replicas)
        return {"replicas": replicas}

    async def pause_rollout(self, namespace: str, deployment: str) -> dict[str, Any]:
        await self._call("pause", namespace, deployment)
        return {"paused": True}


@pytest.fixture
async def sessions(migrated_database_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_database_url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture(autouse=True)
async def no_other_approved_work(sessions: async_sessionmaker[AsyncSession]) -> None:
    """The executor claims any approved proposal; other tests in the session leave some."""
    async with sessions() as session:
        await session.execute(
            sa.update(RemediationProposal)
            .where(
                RemediationProposal.status.in_([ProposalStatus.APPROVED, ProposalStatus.EXECUTING])
            )
            .values(status=ProposalStatus.EXPIRED)
        )
        await session.execute(
            sa.update(RemediationExecution)
            .where(RemediationExecution.status == ExecutionStatus.RUNNING)
            .values(status=ExecutionStatus.FAILED)
        )
        await session.commit()


async def approved(
    sessions: async_sessionmaker[AsyncSession],
    *,
    action: RemediationAction = RemediationAction.ROLLBACK_DEPLOYMENT,
    parameters: dict[str, Any] | None = None,
    expires_in: timedelta = timedelta(minutes=30),
) -> uuid.UUID:
    """An incident in REMEDIATING with one approved proposal; returns the proposal ID."""
    async with sessions() as session:
        org = Organization(name="Acme", slug=f"org-{uuid.uuid4().hex[:10]}")
        session.add(org)
        await session.flush()
        user = User(
            organization_id=org.id,
            issuer="test",
            external_auth_id=uuid.uuid4().hex,
            display_name="Casey Commander",
        )
        incident = Incident(
            organization_id=org.id,
            title="High error rate on Checkout",
            severity=Severity.CRITICAL,
            source="detector",
            status=IncidentStatus.REMEDIATING,
        )
        session.add_all([user, incident])
        await session.flush()
        proposal = RemediationProposal(
            organization_id=org.id,
            incident_id=incident.id,
            action_type=action,
            description="Roll back checkout",
            parameters=parameters
            or {"namespace": "demo", "deployment": "checkout", "to_revision": 6},
            risk_level="medium",
            verification_plan={"window_minutes": 5},
            status=ProposalStatus.APPROVED,
            expires_at=datetime.now(UTC) + expires_in,
        )
        session.add(proposal)
        await session.flush()
        session.add(
            Approval(
                organization_id=org.id,
                proposal_id=proposal.id,
                proposal_version=1,
                requested_by="agent:remediation",
                requested_at=proposal.created_at,
                reviewed_by=user.id,
                reviewer_name=user.display_name,
                decision="approved",
            )
        )
        await session.commit()
        return proposal.id


async def run_once(
    sessions: async_sessionmaker[AsyncSession], writer: FakeWriter
) -> ExecutionStatus | None:
    execution_id = await claim(sessions)
    if execution_id is None:
        return None
    return (await execute(sessions, writer, execution_id, allowed_namespaces=ALLOWED)).status


async def snapshot(sessions: async_sessionmaker[AsyncSession], proposal_id: uuid.UUID) -> Any:
    async with sessions() as session:
        proposal = await session.get_one(RemediationProposal, proposal_id)
        incident = await session.get_one(Incident, proposal.incident_id)
        executions = list(
            await session.scalars(
                sa.select(RemediationExecution).where(
                    RemediationExecution.proposal_id == proposal_id
                )
            )
        )
        events = list(
            await session.scalars(
                sa.select(IncidentEvent.event_type)
                .where(IncidentEvent.incident_id == incident.id)
                .order_by(IncidentEvent.sequence)
            )
        )
        audit = list(
            await session.scalars(
                sa.select(AuditLog.action).where(AuditLog.resource_id == str(proposal_id))
            )
        )
        investigations = list(
            await session.scalars(
                sa.select(Investigation).where(Investigation.incident_id == incident.id)
            )
        )
        return proposal, incident, executions, events, audit, investigations


async def test_an_approved_rollback_runs_once_and_moves_to_verifying(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    proposal_id = await approved(sessions)
    writer = FakeWriter()
    succeeded = {"action": "rollback_deployment", "outcome": "succeeded"}
    before = REGISTRY.get_sample_value("opspilot_remediation_executions_total", succeeded) or 0

    assert await run_once(sessions, writer) is ExecutionStatus.SUCCEEDED
    assert await run_once(sessions, writer) is None
    assert (
        REGISTRY.get_sample_value("opspilot_remediation_executions_total", succeeded) == before + 1
    )

    proposal, incident, [execution], events, audit, _ = await snapshot(sessions, proposal_id)
    assert writer.calls == [("rollback", "demo", "checkout", 6)]
    assert proposal.status is ProposalStatus.EXECUTED
    assert incident.status is IncidentStatus.VERIFYING
    assert execution.idempotency_key == f"{proposal_id}:v1"
    assert execution.output == {"rolled_back_to": 6, "version": "1.0.0"}
    assert execution.completed_at is not None
    assert "incident.remediation_executed" in events
    assert "remediation.executed" in audit


async def test_an_approved_pause_pauses_the_rollout(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    proposal_id = await approved(
        sessions,
        action=RemediationAction.PAUSE_ROLLOUT,
        parameters={"namespace": "demo", "deployment": "checkout", "revision": 7},
    )
    writer = FakeWriter()

    assert await run_once(sessions, writer) is ExecutionStatus.SUCCEEDED

    proposal, incident, [execution], events, audit, _ = await snapshot(sessions, proposal_id)
    assert writer.calls == [("pause", "demo", "checkout")]
    assert execution.output == {"paused": True}
    assert proposal.status is ProposalStatus.EXECUTED
    assert incident.status is IncidentStatus.VERIFYING
    assert "incident.remediation_executed" in events
    assert "remediation.executed" in audit


async def test_concurrent_workers_execute_only_once(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    proposal_id = await approved(sessions)
    writer = FakeWriter()

    results = await asyncio.gather(*(run_once(sessions, writer) for _ in range(4)))

    assert results.count(ExecutionStatus.SUCCEEDED) == 1
    assert len(writer.calls) == 1
    _, _, executions, *_ = await snapshot(sessions, proposal_id)
    assert len(executions) == 1


async def test_rerunning_a_finished_execution_returns_the_stored_result(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    proposal_id = await approved(sessions)
    writer = FakeWriter()
    await run_once(sessions, writer)
    _, _, [execution], *_ = await snapshot(sessions, proposal_id)

    again = await execute(sessions, writer, execution.id, allowed_namespaces=ALLOWED)

    assert again.acted is False
    assert again.status is ExecutionStatus.SUCCEEDED
    assert again.output == execution.output
    assert len(writer.calls) == 1


async def test_an_expired_proposal_does_not_run_and_reopens_the_investigation(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    proposal_id = await approved(sessions, expires_in=-timedelta(seconds=1))
    writer = FakeWriter()
    expired = {"reason": "expired"}
    before = REGISTRY.get_sample_value("opspilot_remediation_blocked_total", expired) or 0

    assert await run_once(sessions, writer) is ExecutionStatus.FAILED
    assert REGISTRY.get_sample_value("opspilot_remediation_blocked_total", expired) == before + 1

    proposal, incident, [execution], events, audit, investigations = await snapshot(
        sessions, proposal_id
    )
    assert writer.calls == []
    assert "expired" in (execution.error_message or "")
    assert proposal.status is ProposalStatus.FAILED
    assert incident.status is IncidentStatus.INVESTIGATING
    assert "incident.remediation_failed" in events
    assert "remediation.failed" in audit
    assert [i.requested_by for i in investigations] == ["worker:remediation"]


async def test_a_disallowed_namespace_is_rejected_before_acting(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    proposal_id = await approved(
        sessions,
        parameters={"namespace": "kube-system", "deployment": "coredns", "to_revision": 1},
    )
    writer = FakeWriter()

    assert await run_once(sessions, writer) is ExecutionStatus.FAILED

    _, _, [execution], *_ = await snapshot(sessions, proposal_id)
    assert writer.calls == []
    assert "kube-system" in (execution.error_message or "")


async def test_an_excessive_replica_count_is_rejected(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    proposal_id = await approved(
        sessions,
        action=RemediationAction.SCALE_DEPLOYMENT,
        parameters={"namespace": "demo", "deployment": "checkout", "replicas": 50},
    )
    writer = FakeWriter()

    assert await run_once(sessions, writer) is ExecutionStatus.FAILED

    _, _, [execution], *_ = await snapshot(sessions, proposal_id)
    assert writer.calls == []
    assert "replicas" in (execution.error_message or "")


async def test_a_proposal_changed_after_approval_does_not_run(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    proposal_id = await approved(sessions)
    async with sessions() as session:
        proposal = await session.get_one(RemediationProposal, proposal_id)
        proposal.parameters = {**proposal.parameters, "to_revision": 1}
        proposal.version = 2
        await session.commit()
    writer = FakeWriter()

    assert await run_once(sessions, writer) is ExecutionStatus.FAILED
    assert writer.calls == []


async def test_a_kubernetes_failure_reopens_the_investigation(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    proposal_id = await approved(sessions)
    writer = FakeWriter(fail=RemediationFailed("revision 6 of checkout no longer exists"))

    assert await run_once(sessions, writer) is ExecutionStatus.FAILED

    _, incident, [execution], *_ = await snapshot(sessions, proposal_id)
    assert execution.error_message == "revision 6 of checkout no longer exists"
    assert incident.status is IncidentStatus.INVESTIGATING


async def test_a_transient_error_is_retried_with_the_same_arguments(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    proposal_id = await approved(
        sessions,
        action=RemediationAction.RESTART_DEPLOYMENT,
        parameters={"namespace": "demo", "deployment": "checkout"},
    )
    writer = FakeWriter(fail=ConnectionError("API server unreachable"))

    assert await run_once(sessions, writer) is ExecutionStatus.RUNNING
    assert await run_once(sessions, writer) is ExecutionStatus.SUCCEEDED

    _, incident, [execution], *_ = await snapshot(sessions, proposal_id)
    first, second = writer.calls
    assert first == second, "a retried restart patches the same timestamp"
    assert execution.attempts == 2
    assert incident.status is IncidentStatus.VERIFYING


async def test_a_dead_workers_execution_is_taken_over(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    proposal_id = await approved(sessions)
    crashed = await claim(sessions)
    assert crashed is not None
    async with sessions() as session:
        execution = await session.get_one(RemediationExecution, crashed)
        execution.lease_until = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    writer = FakeWriter()

    assert await run_once(sessions, writer) is ExecutionStatus.SUCCEEDED

    _, _, [execution], *_ = await snapshot(sessions, proposal_id)
    assert execution.id == crashed
    assert execution.attempts == 2


async def test_proposals_show_their_execution(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    proposal_id = await approved(sessions)
    await run_once(sessions, FakeWriter())

    async with sessions() as session:
        proposal = await session.get_one(RemediationProposal, proposal_id)
        [out] = await proposals_out(session, [proposal])

    assert out.decision is not None
    assert out.decision.reviewer_name == "Casey Commander"
    assert out.execution is not None
    assert out.execution.status is ExecutionStatus.SUCCEEDED
    assert out.execution.output["rolled_back_to"] == 6
