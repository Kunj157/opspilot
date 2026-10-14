"""Reviewing remediation proposals: read one, approve it, or reject it."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.auth.permissions import Permission, require
from opspilot_api.auth.principal import Principal
from opspilot_api.auth.tenancy import get_owned_or_404
from opspilot_api.db.models import RemediationProposal
from opspilot_api.db.session import get_session
from opspilot_api.idempotency import Idempotency, IdempotencyDep
from opspilot_api.incidents.service import IncidentConflictError, InvalidTransitionError
from opspilot_api.remediation.approval import DecisionConflict, ProposalExpired, decide
from opspilot_api.routes.investigations import ProposalOut, proposals_out

router = APIRouter(prefix="/api/v1", tags=["remediation"])


class DecisionIn(BaseModel):
    version: int = Field(ge=1, description="The proposal version that was reviewed")
    comment: str | None = Field(default=None, max_length=1000)


@router.get("/proposals/{proposal_id}", response_model=ProposalOut)
async def get_proposal(
    proposal_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require(Permission.VIEW_INCIDENTS))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProposalOut:
    proposal = await get_owned_or_404(session, RemediationProposal, proposal_id, principal)
    [out] = await proposals_out(session, [proposal])
    return out


async def _decide(
    session: AsyncSession,
    principal: Principal,
    proposal_id: uuid.UUID,
    body: DecisionIn,
    idempotency: Idempotency,
    *,
    approve: bool,
) -> ProposalOut | JSONResponse:
    # Replayed before the version check: a retried approval returns the
    # original outcome, it never executes or fails twice.
    if replay := await idempotency.replay(body):
        return replay
    proposal = await get_owned_or_404(session, RemediationProposal, proposal_id, principal)
    try:
        await decide(
            session,
            proposal,
            principal,
            approve=approve,
            version=body.version,
            comment=body.comment,
        )
    except ProposalExpired as exc:
        # Keep the EXPIRED status and its audit record; a retry replays the 409.
        await idempotency.remember(status.HTTP_409_CONFLICT, {"detail": str(exc)})
        await session.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except (DecisionConflict, IncidentConflictError, InvalidTransitionError) as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.flush()
    [out] = await proposals_out(session, [proposal])
    await idempotency.commit(status.HTTP_200_OK, out)
    return out


@router.post("/proposals/{proposal_id}/approve", response_model=ProposalOut)
async def approve_proposal(
    proposal_id: uuid.UUID,
    body: DecisionIn,
    principal: Annotated[Principal, Depends(require(Permission.APPROVE_REMEDIATION))],
    session: Annotated[AsyncSession, Depends(get_session)],
    idempotency: IdempotencyDep,
) -> ProposalOut | JSONResponse:
    """Approve the reviewed version; the worker then executes it once."""
    return await _decide(session, principal, proposal_id, body, idempotency, approve=True)


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalOut)
async def reject_proposal(
    proposal_id: uuid.UUID,
    body: DecisionIn,
    principal: Annotated[Principal, Depends(require(Permission.APPROVE_REMEDIATION))],
    session: Annotated[AsyncSession, Depends(get_session)],
    idempotency: IdempotencyDep,
) -> ProposalOut | JSONResponse:
    return await _decide(session, principal, proposal_id, body, idempotency, approve=False)
