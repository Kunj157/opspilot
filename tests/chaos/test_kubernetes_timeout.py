"""Kubernetes API timeouts during remediation: bounded, retried identically, then fail safe."""

import json
import time
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from opspilot_api.db.models import (
    AuditLog,
    ExecutionStatus,
    Incident,
    IncidentStatus,
    RemediationAction,
    RemediationExecution,
    RemediationProposal,
)
from opspilot_api.kube import KubernetesWriter
from opspilot_api.remediation.executor import MAX_ATTEMPTS, claim, execute
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.integration.test_remediation_execution import approved

from chaos.harness import Controlled, HangingKubeApi

ALLOWED = frozenset({"demo"})


@pytest.fixture
async def sessions(postgres: Controlled) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(postgres.url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_a_hanging_kubernetes_api_fails_safe_without_double_execution(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    api = HangingKubeApi(hang_seconds=30)
    writer = KubernetesWriter(
        ALLOWED,
        config_file=api.kubeconfig(str(tmp_path / "kubeconfig")),
        context="chaos",
        request_timeout=1.0,
    )
    proposal_id = await approved(
        sessions,
        action=RemediationAction.RESTART_DEPLOYMENT,
        parameters={"namespace": "demo", "deployment": "checkout"},
    )
    try:
        attempts = []
        for _ in range(MAX_ATTEMPTS + 2):
            execution_id = await claim(sessions)
            if execution_id is None:
                break
            started = time.monotonic()
            outcome = await execute(sessions, writer, execution_id, allowed_namespaces=ALLOWED)
            attempts.append((outcome.status, time.monotonic() - started))
    finally:
        api.close()

    # Each attempt gave up after the request timeout instead of hanging the worker.
    assert all(took < 5 for _, took in attempts), attempts
    assert [status for status, _ in attempts] == [ExecutionStatus.RUNNING] * (MAX_ATTEMPTS - 1) + [
        ExecutionStatus.FAILED
    ]
    # Retries sent the identical patch (same restartedAt), one at a time.
    assert len(api.patches) == MAX_ATTEMPTS
    assert len({json.dumps(json.loads(p), sort_keys=True) for p in api.patches}) == 1
    # Sequential: each retry started only after the previous attempt timed out.
    gaps = [b - a for a, b in zip(api.received, api.received[1:], strict=False)]
    assert all(gap >= 0.9 for gap in gaps), gaps

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
        audit = list(
            await session.scalars(
                sa.select(AuditLog.action).where(AuditLog.resource_id == str(proposal_id))
            )
        )
    assert len(executions) == 1
    assert executions[0].status is ExecutionStatus.FAILED
    assert "gave up after" in (executions[0].error_message or "")
    assert "remediation.failed" in audit
    assert incident.status is IncidentStatus.INVESTIGATING, "reopened for a new investigation"
