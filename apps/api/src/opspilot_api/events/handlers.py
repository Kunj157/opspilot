"""What consumers do with events.

Every stage moves from a polling or direct call to its event in two steps:
shadow mode only compares what the event would do with what the existing
path already did (counted per stage), and authoritative mode makes the
event the trigger, with the old path kept as a slow fallback.
"""

import uuid

from prometheus_client import Counter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opspilot_api.agents.queue import enqueue
from opspilot_api.db.models import (
    Incident,
    IncidentStatus,
    Investigation,
    ProposalStatus,
    RemediationExecution,
    RemediationProposal,
)
from opspilot_api.events.consumer import Handler, PermanentError
from opspilot_api.events.envelope import Envelope
from opspilot_api.kube import KubeReader, KubeWriter
from opspilot_api.remediation.executor import claim, execute
from opspilot_api.remediation.verification import verify
from opspilot_api.telemetry import MetricsProvider

SHADOW_AGREEMENT = Counter(
    "opspilot_event_shadow_agreement_total",
    "Shadow consumer decisions compared with the direct call",
    ["stage", "agrees"],
)
REQUESTER = "event:incident.created.v1"


def investigation_requester(*, authoritative: bool) -> Handler:
    """incident.created.v1 → queue an investigation for detector incidents.

    In shadow mode it only checks that the direct call already did what the
    event would have done, and counts agreement; once authoritative it queues
    the investigation itself (enqueue is idempotent per incident).
    """

    async def handle(session: AsyncSession, envelope: Envelope) -> str:
        try:
            incident_id = uuid.UUID(str(envelope.payload["incident_id"]))
        except (KeyError, ValueError) as exc:
            raise PermanentError(f"no incident in payload: {exc}") from exc
        incident = await session.get(Incident, incident_id)
        if incident is None or incident.organization_id != envelope.organization_id:
            raise PermanentError(f"unknown incident {incident_id}")
        if incident.source != "detector":
            return "skipped: not a detector incident"
        if incident.status is IncidentStatus.RESOLVED:
            # Out of order: the incident ended before this event was handled.
            return "skipped: already resolved"
        if not authoritative:
            existing = await session.scalar(
                select(Investigation.id).where(Investigation.incident_id == incident.id).limit(1)
            )
            SHADOW_AGREEMENT.labels("investigation", str(existing is not None).lower()).inc()
            return "shadow: agrees" if existing else "shadow: direct call queued nothing"
        _, created = await enqueue(session, incident, REQUESTER)
        return "queued" if created else "already queued"

    return handle


def _uuid(envelope: Envelope, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(envelope.payload[field]))
    except (KeyError, ValueError) as exc:
        raise PermanentError(f"no {field} in payload: {exc}") from exc


def remediation_executor(
    *,
    authoritative: bool,
    sessions: async_sessionmaker[AsyncSession],
    writer: KubeWriter,
    allowed_namespaces: frozenset[str],
) -> Handler:
    """incident.remediation.approved.v1 → run the approved proposal.

    Shadow mode checks the polling executor already picked the proposal up.
    Authoritative mode claims exactly this proposal and runs it; the claim's
    idempotency key and lease keep it to one execution even if the fallback
    sweep or a redelivery races it.
    """

    async def handle(session: AsyncSession, envelope: Envelope) -> str:
        proposal = await session.get(RemediationProposal, _uuid(envelope, "proposal_id"))
        if proposal is None or proposal.organization_id != envelope.organization_id:
            raise PermanentError("unknown proposal")
        if not authoritative:
            started = await session.scalar(
                select(RemediationExecution.id)
                .where(RemediationExecution.proposal_id == proposal.id)
                .limit(1)
            )
            agrees = started is not None or proposal.status is not ProposalStatus.APPROVED
            SHADOW_AGREEMENT.labels("remediation", str(agrees).lower()).inc()
            return "shadow: agrees" if agrees else "shadow: polling has not started it"
        if proposal.status is not ProposalStatus.APPROVED:
            return f"skipped: proposal is {proposal.status.value.lower()}"
        execution_id = await claim(sessions, proposal_id=proposal.id)
        if execution_id is None:
            return "skipped: already running"
        outcome = await execute(
            sessions, writer, execution_id, allowed_namespaces=allowed_namespaces
        )
        return f"executed: {outcome.status.value.lower()}"

    return handle


def verification_starter(
    *,
    authoritative: bool,
    sessions: async_sessionmaker[AsyncSession],
    kube: KubeReader,
    metrics: MetricsProvider,
) -> Handler:
    """incident.remediation.completed.v1 → take the first verification look now.

    Verification waits for the rollout and a full traffic window, so later
    looks stay on the verification timer; the event removes the polling
    delay before the first one. Shadow mode checks the execution is queued
    for verification.
    """

    async def handle(session: AsyncSession, envelope: Envelope) -> str:
        if envelope.payload.get("outcome") != "succeeded":
            return "skipped: remediation failed"
        execution = await session.get(RemediationExecution, _uuid(envelope, "execution_id"))
        if execution is None or execution.organization_id != envelope.organization_id:
            raise PermanentError("unknown execution")
        if not authoritative:
            agrees = execution.verification_status is not None
            SHADOW_AGREEMENT.labels("verification", str(agrees).lower()).inc()
            return "shadow: agrees" if agrees else "shadow: not queued for verification"
        if execution.verification_status != "pending":
            return f"skipped: verification {execution.verification_status}"
        verdict = await verify(sessions, kube, metrics, execution.id)
        if verdict is None:
            return "verification started"
        return "verification passed" if verdict.passed else "verification failed"

    return handle
