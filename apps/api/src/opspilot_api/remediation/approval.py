"""Human decisions on remediation proposals.

A decision names the proposal version the reviewer saw; any change to the
proposal bumps its version, so a stale review is refused. The proposal row is
locked while deciding, so concurrent reviewers cannot both decide.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.audit.service import record
from opspilot_api.auth.principal import Principal
from opspilot_api.db.models import (
    Approval,
    Incident,
    IncidentStatus,
    ProposalStatus,
    RemediationProposal,
)
from opspilot_api.incidents import service as incidents
from opspilot_api.request_context import current_request_id


class DecisionConflict(Exception):
    """The proposal cannot be decided as asked; the message says why."""


class ProposalExpired(DecisionConflict):
    """The proposal expired before it was approved; it is now EXPIRED (caller commits)."""


async def decide(
    session: AsyncSession,
    proposal: RemediationProposal,
    principal: Principal,
    *,
    approve: bool,
    version: int,
    comment: str | None,
) -> Approval:
    """Record the decision and move the incident on; the caller commits."""
    # Re-read under a row lock: whoever gets it first decides.
    await session.refresh(proposal, with_for_update=True)
    if proposal.status is not ProposalStatus.PENDING:
        raise DecisionConflict(f"The proposal is already {proposal.status.value.lower()}")
    if proposal.version != version:
        raise DecisionConflict(
            f"The proposal changed since you reviewed it (version {version}, "
            f"now {proposal.version}); review it again"
        )
    if approve and proposal.expires_at and proposal.expires_at <= datetime.now(UTC):
        proposal.status = ProposalStatus.EXPIRED
        await record(
            session,
            principal=principal,
            action="remediation.expired",
            resource_type="remediation_proposal",
            resource_id=str(proposal.id),
        )
        raise ProposalExpired("The proposal expired; run the investigation again")
    incident = await session.get_one(Incident, proposal.incident_id, with_for_update=True)
    if incident.status is not IncidentStatus.AWAITING_APPROVAL:
        raise DecisionConflict(f"The incident is {incident.status.value}, not awaiting approval")

    decision = "approved" if approve else "rejected"
    approval = Approval(
        organization_id=proposal.organization_id,
        proposal_id=proposal.id,
        proposal_version=proposal.version,
        requested_by="agent:remediation",
        requested_at=proposal.created_at,
        reviewed_by=principal.user_id,
        reviewer_name=principal.display_name,
        decision=decision,
        comment=comment,
        request_id=current_request_id.get(),
    )
    session.add(approval)
    proposal.status = ProposalStatus.APPROVED if approve else ProposalStatus.REJECTED
    if approve:
        # One remediation at a time: the other open proposals are superseded.
        others = await session.scalars(
            select(RemediationProposal).where(
                RemediationProposal.incident_id == incident.id,
                RemediationProposal.id != proposal.id,
                RemediationProposal.status == ProposalStatus.PENDING,
            )
        )
        for other in others:
            other.status = ProposalStatus.SUPERSEDED

    actor = incidents.Actor.from_principal(principal)
    metadata = {
        "proposal_id": str(proposal.id),
        "proposal_version": proposal.version,
        "action_type": proposal.action_type.value,
        "parameters": proposal.parameters,
        "comment": comment,
    }
    await incidents.note(
        session,
        incident,
        actor,
        event_type=f"incident.remediation_{decision}",
        title=f"{principal.display_name} {decision} the {_label(proposal)}",
        metadata=metadata,
    )
    await incidents.transition(
        session,
        incident,
        IncidentStatus.REMEDIATING if approve else IncidentStatus.REJECTED,
        expected_version=incident.version,
        actor=actor,
        reason=f"remediation {decision}",
    )
    await record(
        session,
        principal=principal,
        action=f"remediation.{decision}",
        resource_type="remediation_proposal",
        resource_id=str(proposal.id),
        metadata=metadata,
    )
    await session.flush()
    return approval


def _label(proposal: RemediationProposal) -> str:
    return proposal.action_type.value.lower().replace("_", " ")
