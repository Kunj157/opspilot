"""Agent investigations of an incident: start one, and read its results."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.agents.queue import enqueue
from opspilot_api.audit.service import record
from opspilot_api.auth.permissions import Permission, require
from opspilot_api.auth.principal import Principal
from opspilot_api.auth.tenancy import get_owned_or_404
from opspilot_api.db.models import (
    AgentRun,
    AgentToolCall,
    Approval,
    Evidence,
    Incident,
    IncidentStatus,
    Investigation,
    InvestigationStatus,
    Postmortem,
    ProposalStatus,
    RemediationAction,
    RemediationProposal,
)
from opspilot_api.db.session import get_session

router = APIRouter(prefix="/api/v1", tags=["investigations"])


class InvestigationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    incident_id: uuid.UUID
    status: InvestigationStatus
    current_node: str | None
    round: int
    result: dict[str, Any] | None
    error: str | None
    tool_calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    evidence_type: str
    source: str
    summary: str
    content: dict[str, Any]
    query: str | None
    time_range_start: datetime | None
    time_range_end: datetime | None
    confidence: float
    created_at: datetime


class ToolCallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tool_name: str
    arguments: dict[str, Any]
    status: str
    result_summary: str | None
    error: str | None
    duration_ms: float
    created_at: datetime


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_name: str
    status: str
    model_provider: str
    model_name: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    latency_ms: float
    error_code: str | None
    output: dict[str, Any] | None
    started_at: datetime
    completed_at: datetime | None
    tool_calls: list[ToolCallOut] = []


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    decision: str
    proposal_version: int
    reviewed_by: uuid.UUID
    reviewer_name: str
    comment: str | None
    reviewed_at: datetime


class ProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action_type: RemediationAction
    description: str
    parameters: dict[str, Any]
    risk_level: str
    status: ProposalStatus
    verification_plan: dict[str, Any]
    evidence_ids: list[str]
    runbook_id: uuid.UUID | None
    version: int
    expires_at: datetime | None
    created_at: datetime
    decision: DecisionOut | None = None


async def proposals_out(
    session: AsyncSession, proposals: list[RemediationProposal]
) -> list[ProposalOut]:
    """Proposals with the decision taken on each, if any."""
    approvals = {
        a.proposal_id: a
        for a in await session.scalars(
            select(Approval).where(Approval.proposal_id.in_([p.id for p in proposals]))
        )
    }
    out = []
    for proposal in proposals:
        item = ProposalOut.model_validate(proposal)
        if approval := approvals.get(proposal.id):
            item.decision = DecisionOut.model_validate(approval)
        out.append(item)
    return out


class Items[T](BaseModel):
    items: list[T]


async def _incident(
    session: AsyncSession, incident_id: uuid.UUID, principal: Principal
) -> Incident:
    return await get_owned_or_404(session, Incident, incident_id, principal)


@router.post(
    "/incidents/{incident_id}/investigation",
    response_model=InvestigationOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses={200: {"model": InvestigationOut, "description": "Already investigating"}},
)
async def start_investigation(
    incident_id: uuid.UUID,
    response: Response,
    principal: Annotated[Principal, Depends(require(Permission.START_INVESTIGATION))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InvestigationOut:
    """Queue an agent investigation; returns the running one if there already is one."""
    incident = await _incident(session, incident_id, principal)
    investigation, created = await enqueue(session, incident, f"user:{principal.user_id}")
    if created:
        await session.flush()
        await record(
            session,
            principal=principal,
            action="investigation.requested",
            resource_type="investigation",
            resource_id=str(investigation.id),
            metadata={"incident_id": str(incident.id)},
        )
    else:
        response.status_code = status.HTTP_200_OK
    await session.commit()
    await session.refresh(investigation)
    return InvestigationOut.model_validate(investigation)


@router.get("/incidents/{incident_id}/investigation", response_model=InvestigationOut)
async def latest_investigation(
    incident_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require(Permission.VIEW_INCIDENTS))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InvestigationOut:
    await _incident(session, incident_id, principal)
    investigation = await session.scalar(
        select(Investigation)
        .where(Investigation.incident_id == incident_id)
        .order_by(Investigation.created_at.desc())
        .limit(1)
    )
    if investigation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No investigation yet")
    return InvestigationOut.model_validate(investigation)


@router.get("/incidents/{incident_id}/evidence", response_model=Items[EvidenceOut])
async def list_evidence(
    incident_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require(Permission.VIEW_INCIDENTS))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Items[EvidenceOut]:
    await _incident(session, incident_id, principal)
    rows = await session.scalars(
        select(Evidence).where(Evidence.incident_id == incident_id).order_by(Evidence.created_at)
    )
    return Items[EvidenceOut](items=[EvidenceOut.model_validate(r) for r in rows])


@router.get("/incidents/{incident_id}/agent-runs", response_model=Items[AgentRunOut])
async def list_agent_runs(
    incident_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require(Permission.VIEW_INCIDENTS))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Items[AgentRunOut]:
    await _incident(session, incident_id, principal)
    runs = list(
        await session.scalars(
            select(AgentRun)
            .where(AgentRun.incident_id == incident_id)
            .order_by(AgentRun.started_at)
        )
    )
    calls = list(
        await session.scalars(
            select(AgentToolCall)
            .where(AgentToolCall.agent_run_id.in_([r.id for r in runs]))
            .order_by(AgentToolCall.created_at)
        )
    )
    out = []
    for run in runs:
        item = AgentRunOut.model_validate(run)
        item.tool_calls = [ToolCallOut.model_validate(c) for c in calls if c.agent_run_id == run.id]
        out.append(item)
    return Items[AgentRunOut](items=out)


@router.get("/incidents/{incident_id}/proposals", response_model=Items[ProposalOut])
async def list_proposals(
    incident_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require(Permission.VIEW_INCIDENTS))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Items[ProposalOut]:
    await _incident(session, incident_id, principal)
    rows = await session.scalars(
        select(RemediationProposal)
        .where(RemediationProposal.incident_id == incident_id)
        .order_by(RemediationProposal.created_at.desc())
    )
    return Items[ProposalOut](items=await proposals_out(session, list(rows)))


class PostmortemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    content: dict[str, Any] | None
    generated_by: str | None
    prompt_version: str | None
    updated_at: datetime


@router.get("/incidents/{incident_id}/postmortem", response_model=PostmortemOut)
async def get_postmortem(
    incident_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require(Permission.VIEW_INCIDENTS))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PostmortemOut:
    await _incident(session, incident_id, principal)
    postmortem = await session.scalar(
        select(Postmortem).where(Postmortem.incident_id == incident_id)
    )
    if postmortem is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No postmortem yet")
    return PostmortemOut.model_validate(postmortem)


@router.post(
    "/incidents/{incident_id}/postmortem",
    response_model=PostmortemOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_postmortem(
    incident_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require(Permission.MANAGE_INCIDENTS))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PostmortemOut:
    """Ask the worker to (re)draft the postmortem of a resolved incident."""
    incident = await _incident(session, incident_id, principal)
    if incident.status is not IncidentStatus.RESOLVED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only resolved incidents get a postmortem")
    postmortem = await session.scalar(
        select(Postmortem).where(Postmortem.incident_id == incident_id)
    )
    if postmortem is None:
        postmortem = Postmortem(organization_id=incident.organization_id, incident_id=incident.id)
        session.add(postmortem)
    postmortem.status = "pending"
    await session.flush()
    await record(
        session,
        principal=principal,
        action="postmortem.requested",
        resource_type="incident",
        resource_id=str(incident.id),
    )
    await session.commit()
    await session.refresh(postmortem)
    return PostmortemOut.model_validate(postmortem)
