"""Approval → execution and execution → verification driven by events, shadow then switched."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opspilot_api.db.models import (
    ExecutionStatus,
    ProposalStatus,
    RemediationExecution,
    RemediationProposal,
)
from opspilot_api.events.consumer import EventProcessor
from opspilot_api.events.handlers import remediation_executor, verification_starter
from opspilot_api.remediation.executor import claim
from opspilot_api.remediation.verification import pending
from tests.integration.test_recovery_verification import EXECUTED, Kube, Metrics, executed
from tests.integration.test_remediation_execution import (
    ALLOWED,
    FakeWriter,
    approved,
    no_other_approved_work,
)
from tests.support.events import Recorder

pytestmark = pytest.mark.integration
__all__ = ["no_other_approved_work"]  # autouse: other tests leave approved work behind

APPROVED = "incident.remediation.approved.v1"
COMPLETED = "incident.remediation.completed.v1"


def event(topic: str, organization_id: uuid.UUID, payload: dict[str, Any]) -> bytes:
    return json.dumps(
        {
            "event_id": str(uuid.uuid4()),
            "event_type": topic,
            "event_version": 1,
            "organization_id": str(organization_id),
            "correlation_id": str(uuid.uuid4()),
            "causation_id": None,
            "occurred_at": datetime.now(UTC).isoformat(),
            "producer": "api",
            "payload": payload,
        }
    ).encode()


async def proposal(sessions: async_sessionmaker[AsyncSession], pid: uuid.UUID) -> Any:
    async with sessions() as session:
        return await session.get_one(RemediationProposal, pid)


def executor(
    sessions: async_sessionmaker[AsyncSession], writer: FakeWriter, *, authoritative: bool
) -> EventProcessor:
    handler = remediation_executor(
        authoritative=authoritative, sessions=sessions, writer=writer, allowed_namespaces=ALLOWED
    )
    return EventProcessor(f"remediation-{uuid.uuid4().hex[:6]}", sessions, handler, Recorder())


async def test_an_approval_event_runs_the_proposal_exactly_once(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    pid = await approved(sessions)
    org = (await proposal(sessions, pid)).organization_id
    writer = FakeWriter()
    p = executor(sessions, writer, authoritative=True)

    first = await p.process(APPROVED, b"k", event(APPROVED, org, {"proposal_id": str(pid)}))
    redelivered = await p.process(APPROVED, b"k", event(APPROVED, org, {"proposal_id": str(pid)}))

    assert first.detail == "executed: succeeded"
    assert redelivered.detail == "skipped: proposal is executed"
    assert [c[0] for c in writer.calls] == ["rollback"]
    assert (await proposal(sessions, pid)).status is ProposalStatus.EXECUTED


async def test_shadow_mode_only_checks_that_polling_started_it(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    pid = await approved(sessions)
    org = (await proposal(sessions, pid)).organization_id
    writer = FakeWriter()
    p = executor(sessions, writer, authoritative=False)

    before = await p.process(APPROVED, b"k", event(APPROVED, org, {"proposal_id": str(pid)}))
    assert await claim(sessions) is not None
    after = await p.process(APPROVED, b"k", event(APPROVED, org, {"proposal_id": str(pid)}))

    assert before.detail == "shadow: polling has not started it"
    assert after.detail == "shadow: agrees"
    assert writer.calls == []


async def test_an_approval_event_from_another_organization_is_parked(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    pid = await approved(sessions)
    writer = FakeWriter()

    result = await executor(sessions, writer, authoritative=True).process(
        APPROVED, b"k", event(APPROVED, uuid.uuid4(), {"proposal_id": str(pid)})
    )

    assert result.outcome == "dead_lettered"
    assert writer.calls == []
    assert (await proposal(sessions, pid)).status is ProposalStatus.APPROVED


async def test_the_fallback_sweep_leaves_fresh_approvals_to_their_event(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await approved(sessions)

    assert await claim(sessions, approved_before=datetime.now(UTC) - timedelta(minutes=1)) is None
    assert await claim(sessions, approved_before=datetime.now(UTC) + timedelta(seconds=1))


def starter(
    sessions: async_sessionmaker[AsyncSession], *, authoritative: bool, kube: Kube | None = None
) -> EventProcessor:
    handler = verification_starter(
        authoritative=authoritative, sessions=sessions, kube=kube or Kube(), metrics=Metrics()
    )
    return EventProcessor(f"verification-{uuid.uuid4().hex[:6]}", sessions, handler, Recorder())


async def execution(sessions: async_sessionmaker[AsyncSession], eid: uuid.UUID) -> Any:
    async with sessions() as session:
        return await session.get_one(RemediationExecution, eid)


async def test_a_completion_event_takes_the_first_verification_look(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    eid = await executed(sessions)
    current = await execution(sessions, eid)
    payload = {"execution_id": str(eid), "outcome": "succeeded"}

    result = await starter(sessions, authoritative=True).process(
        COMPLETED, b"k", event(COMPLETED, current.organization_id, payload)
    )

    assert result.detail == "verification started"
    assert (await execution(sessions, eid)).rollout_completed_at is not None


async def test_shadow_verification_only_checks_the_execution_is_queued(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    eid = await executed(sessions)
    current = await execution(sessions, eid)
    payload = {"execution_id": str(eid), "outcome": "succeeded"}

    result = await starter(sessions, authoritative=False).process(
        COMPLETED, b"k", event(COMPLETED, current.organization_id, payload)
    )

    assert result.detail == "shadow: agrees"
    assert (await execution(sessions, eid)).rollout_completed_at is None


async def test_a_failed_remediation_is_not_verified(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    eid = await executed(sessions)
    current = await execution(sessions, eid)
    payload = {"execution_id": str(eid), "outcome": "failed"}

    result = await starter(sessions, authoritative=True).process(
        COMPLETED, b"k", event(COMPLETED, current.organization_id, payload)
    )

    assert result.detail == "skipped: remediation failed"
    assert (await execution(sessions, eid)).status is ExecutionStatus.SUCCEEDED


async def test_polling_waits_before_taking_over_from_the_event(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    eid = await executed(sessions)

    assert eid not in await pending(sessions, completed_before=EXECUTED - timedelta(seconds=30))
    assert eid in await pending(sessions, completed_before=datetime.now(UTC))
