"""Runs approved remediation proposals exactly once.

A worker claims an approved proposal with SELECT ... FOR UPDATE SKIP LOCKED
and creates its execution under a unique idempotency key
("<proposal>:v<version>"), so two workers can never both run it. Running an
execution that already finished returns the stored result. A worker that
dies mid-run leaves an expired lease, and another worker retries the same
execution with the same arguments; every Kubernetes action is idempotent for
fixed arguments, so the retry cannot act twice.

Parameters are checked again just before acting: the proposal must still be
approved and unexpired, the namespace allow-listed, and the bounds respected.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opspilot_api.agents.policy import MAX_REPLICAS
from opspilot_api.agents.queue import enqueue
from opspilot_api.audit.service import record
from opspilot_api.db.models import (
    ActorType,
    Approval,
    ExecutionStatus,
    Incident,
    IncidentStatus,
    ProposalStatus,
    RemediationAction,
    RemediationExecution,
    RemediationProposal,
)
from opspilot_api.incidents import service as incidents
from opspilot_api.kube import KubeWriter, NamespaceNotAllowed, RemediationFailed

log = structlog.get_logger("opspilot.remediation")

ACTOR_ID = "worker:remediation"
LEASE = timedelta(minutes=5)
MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class Outcome:
    status: ExecutionStatus
    output: dict[str, Any]
    error: str | None
    acted: bool  # False when the stored result of an earlier run was returned


def idempotency_key(proposal: RemediationProposal) -> str:
    return f"{proposal.id}:v{proposal.version}"


async def claim(sessions: async_sessionmaker[AsyncSession]) -> uuid.UUID | None:
    """Start the execution of one approved proposal, or take over one whose lease expired."""
    now = datetime.now(UTC)
    async with sessions() as session:
        proposal = await session.scalar(
            select(RemediationProposal)
            .where(RemediationProposal.status == ProposalStatus.APPROVED)
            .order_by(RemediationProposal.updated_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if proposal is not None:
            await session.execute(
                insert(RemediationExecution)
                .values(
                    organization_id=proposal.organization_id,
                    proposal_id=proposal.id,
                    incident_id=proposal.incident_id,
                    idempotency_key=idempotency_key(proposal),
                )
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
            )
            proposal.status = ProposalStatus.EXECUTING
        execution = await session.scalar(
            select(RemediationExecution)
            .where(
                RemediationExecution.status == ExecutionStatus.RUNNING,
                or_(
                    RemediationExecution.lease_until.is_(None),
                    RemediationExecution.lease_until < now,
                ),
            )
            .order_by(RemediationExecution.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if execution is None:
            await session.commit()
            return None
        execution.attempts += 1
        execution.lease_until = now + LEASE
        await session.commit()
        return execution.id


async def execute(
    sessions: async_sessionmaker[AsyncSession],
    writer: KubeWriter,
    execution_id: uuid.UUID,
    *,
    allowed_namespaces: frozenset[str],
) -> Outcome:
    async with sessions() as session:
        execution = await session.get_one(RemediationExecution, execution_id)
        if execution.status is not ExecutionStatus.RUNNING:
            return Outcome(execution.status, execution.output, execution.error_message, False)
        proposal = await session.get_one(RemediationProposal, execution.proposal_id)
        approval = await session.scalar(select(Approval).where(Approval.proposal_id == proposal.id))
        attempts = execution.attempts
        started_at = execution.started_at

    error: str | None = None
    output: dict[str, Any] = {}
    try:
        problem = _recheck(proposal, approval, execution_id, allowed_namespaces)
        if problem:
            raise RemediationFailed(problem)
        output = await _act(writer, proposal, started_at)
    except (RemediationFailed, NamespaceNotAllowed) as exc:
        error = str(exc)
    except Exception as exc:
        # Possibly transient (API unreachable): retry on the next lease, up to a limit.
        log.exception("remediation attempt failed", execution_id=str(execution_id))
        if attempts < MAX_ATTEMPTS:
            async with sessions() as session:
                execution = await session.get_one(RemediationExecution, execution_id)
                execution.lease_until = datetime.now(UTC)
                await session.commit()
            return Outcome(ExecutionStatus.RUNNING, {}, str(exc), False)
        error = f"gave up after {attempts} attempts: {exc}"
    return await _finish(sessions, execution_id, output, error, approval)


def _recheck(
    proposal: RemediationProposal,
    approval: Approval | None,
    execution_id: uuid.UUID,
    allowed: frozenset[str],
) -> str | None:
    p = proposal.parameters
    if approval is None or approval.decision != "approved":
        return "the proposal has no approval"
    if approval.proposal_version != proposal.version:
        return "the proposal changed after it was approved"
    if proposal.expires_at and proposal.expires_at <= datetime.now(UTC):
        return "the proposal expired before it could run"
    if p.get("namespace") not in allowed:
        return f"namespace {p.get('namespace')!r} is not allowed"
    if not p.get("deployment"):
        return "the proposal names no deployment"
    if proposal.action_type is RemediationAction.ROLLBACK_DEPLOYMENT and not isinstance(
        p.get("to_revision"), int
    ):
        return "the rollback names no revision"
    if proposal.action_type is RemediationAction.SCALE_DEPLOYMENT and not (
        isinstance(p.get("replicas"), int) and 1 <= p["replicas"] <= MAX_REPLICAS
    ):
        return f"replicas must be between 1 and {MAX_REPLICAS}"
    if proposal.action_type not in EXECUTABLE:
        return f"{proposal.action_type.value} cannot be executed"
    return None


EXECUTABLE = {
    RemediationAction.ROLLBACK_DEPLOYMENT,
    RemediationAction.RESTART_DEPLOYMENT,
    RemediationAction.SCALE_DEPLOYMENT,
    RemediationAction.PAUSE_ROLLOUT,
}


async def _act(
    writer: KubeWriter, proposal: RemediationProposal, started_at: datetime
) -> dict[str, Any]:
    p = proposal.parameters
    namespace, deployment = p["namespace"], p["deployment"]
    match proposal.action_type:
        case RemediationAction.ROLLBACK_DEPLOYMENT:
            return await writer.rollback_deployment(
                namespace,
                deployment,
                p["to_revision"],
                cause=f"OpsPilot rollback to revision {p['to_revision']} (proposal {proposal.id})",
            )
        case RemediationAction.RESTART_DEPLOYMENT:
            # A fixed timestamp per execution: a retried restart patches the same value.
            return await writer.restart_deployment(
                namespace, deployment, restarted_at=started_at.isoformat()
            )
        case RemediationAction.PAUSE_ROLLOUT:
            return await writer.pause_rollout(namespace, deployment)
        case _:
            return await writer.scale_deployment_within_bounds(
                namespace, deployment, p["replicas"], maximum=MAX_REPLICAS
            )


async def _finish(
    sessions: async_sessionmaker[AsyncSession],
    execution_id: uuid.UUID,
    output: dict[str, Any],
    error: str | None,
    approval: Approval | None,
) -> Outcome:
    async with sessions() as session:
        execution = await session.get_one(RemediationExecution, execution_id, with_for_update=True)
        if execution.status is not ExecutionStatus.RUNNING:
            return Outcome(execution.status, execution.output, execution.error_message, False)
        proposal = await session.get_one(RemediationProposal, execution.proposal_id)
        incident = await session.get_one(Incident, execution.incident_id)
        ok = error is None
        execution.status = ExecutionStatus.SUCCEEDED if ok else ExecutionStatus.FAILED
        execution.output = output
        execution.error_message = error
        execution.completed_at = datetime.now(UTC)
        execution.lease_until = None
        execution.verification_status = "pending" if ok else None
        proposal.status = ProposalStatus.EXECUTED if ok else ProposalStatus.FAILED

        actor = incidents.Actor(ActorType.SYSTEM, ACTOR_ID, incident.organization_id)
        metadata = {
            "proposal_id": str(proposal.id),
            "execution_id": str(execution.id),
            "action_type": proposal.action_type.value,
            "parameters": proposal.parameters,
            "approved_by": approval.reviewer_name if approval else None,
            "output": output,
            "error": error,
        }
        await incidents.note(
            session,
            incident,
            actor,
            event_type="incident.remediation_executed" if ok else "incident.remediation_failed",
            title=_title(proposal, output) if ok else f"Remediation failed: {error}",
            metadata=metadata,
        )
        await record(
            session,
            organization_id=incident.organization_id,
            actor_type=ActorType.SYSTEM,
            actor_id=ACTOR_ID,
            action="remediation.executed" if ok else "remediation.failed",
            resource_type="remediation_proposal",
            resource_id=str(proposal.id),
            metadata=metadata,
        )
        if incident.status is IncidentStatus.REMEDIATING:
            await incidents.transition(
                session,
                incident,
                IncidentStatus.VERIFYING,
                expected_version=incident.version,
                actor=actor,
                reason="remediation executed" if ok else "remediation failed",
            )
            if not ok:
                await reopen(session, incident, actor, f"remediation failed: {error}")
        await session.commit()
        log.info(
            "remediation finished",
            execution_id=str(execution.id),
            action=proposal.action_type.value,
            ok=ok,
            error=error,
        )
        return Outcome(execution.status, output, error, True)


async def reopen(
    session: AsyncSession, incident: Incident, actor: incidents.Actor, reason: str
) -> None:
    """Back to investigating, with a new investigation queued. The caller commits."""
    await incidents.transition(
        session,
        incident,
        IncidentStatus.INVESTIGATING,
        expected_version=incident.version,
        actor=actor,
        reason=reason,
    )
    await enqueue(session, incident, ACTOR_ID)


def _title(proposal: RemediationProposal, output: dict[str, Any]) -> str:
    p = proposal.parameters
    match proposal.action_type:
        case RemediationAction.ROLLBACK_DEPLOYMENT:
            version = f" ({output['version']})" if output.get("version") else ""
            return f"Rolled back {p['deployment']} to revision {p['to_revision']}{version}"
        case RemediationAction.RESTART_DEPLOYMENT:
            return f"Restarted {p['deployment']}"
        case RemediationAction.PAUSE_ROLLOUT:
            return f"Paused the rollout of {p['deployment']}"
        case _:
            return f"Scaled {p['deployment']} to {p.get('replicas')} replicas"
