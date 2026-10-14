"""Approving and rejecting remediation proposals: roles, versions, expiry, tenancy, audit."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from opspilot_api.db.models import (
    Approval,
    AuditLog,
    Incident,
    IncidentEvent,
    IncidentStatus,
    ProposalStatus,
    RemediationAction,
    RemediationProposal,
    User,
)
from tests.support.app import Caller, api_client, new_org
from tests.support.tokens import TokenFactory

pytestmark = pytest.mark.integration


@pytest.fixture
def factory() -> TokenFactory:
    return TokenFactory()


@pytest.fixture
async def client(
    migrated_database_url: str, factory: TokenFactory
) -> AsyncIterator[httpx.AsyncClient]:
    async with api_client(migrated_database_url, factory) as c:
        yield c


@pytest.fixture
async def sessions(migrated_database_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_database_url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def awaiting_approval(
    client: httpx.AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    caller: Caller,
    *,
    expires_in: timedelta = timedelta(minutes=30),
) -> tuple[str, str]:
    """An incident awaiting approval of one pending rollback proposal: (incident, proposal)."""
    created = await client.post(
        "/api/v1/incidents",
        json={"title": "Checkout errors", "severity": "high"},
        headers=caller.headers,
    )
    incident_id = uuid.UUID(created.json()["id"])
    async with sessions() as session:
        incident = await session.get_one(Incident, incident_id)
        incident.status = IncidentStatus.AWAITING_APPROVAL
        proposal = RemediationProposal(
            organization_id=incident.organization_id,
            incident_id=incident.id,
            action_type=RemediationAction.ROLLBACK_DEPLOYMENT,
            description="Roll back checkout to revision 6 (1.0.0)",
            parameters={"namespace": "demo", "deployment": "checkout", "to_revision": 6},
            risk_level="medium",
            verification_plan={"window_minutes": 3},
            expires_at=datetime.now(UTC) + expires_in,
        )
        session.add(proposal)
        await session.commit()
        return str(incident_id), str(proposal.id)


@dataclass
class Snapshot:
    incident: IncidentStatus
    proposal: ProposalStatus
    approvals: list[Approval]
    audit: list[str]
    events: list[str]


async def state(
    sessions: async_sessionmaker[AsyncSession], incident_id: str, proposal_id: str
) -> Snapshot:
    async with sessions() as session:
        return Snapshot(
            incident=(await session.get_one(Incident, uuid.UUID(incident_id))).status,
            proposal=(await session.get_one(RemediationProposal, uuid.UUID(proposal_id))).status,
            approvals=list(
                await session.scalars(
                    sa.select(Approval).where(Approval.proposal_id == uuid.UUID(proposal_id))
                )
            ),
            audit=list(
                await session.scalars(
                    sa.select(AuditLog.action).where(AuditLog.resource_id == proposal_id)
                )
            ),
            events=list(
                await session.scalars(
                    sa.select(IncidentEvent.event_type)
                    .where(IncidentEvent.incident_id == uuid.UUID(incident_id))
                    .order_by(IncidentEvent.sequence)
                )
            ),
        )


async def test_a_commander_approves_the_reviewed_version(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession], factory: TokenFactory
) -> None:
    commander = Caller(factory, new_org(), "incident-commander")
    incident_id, proposal_id = await awaiting_approval(client, sessions, commander)

    response = await client.post(
        f"/api/v1/proposals/{proposal_id}/approve",
        json={"version": 1, "comment": "Errors began with 1.4.2"},
        headers={**commander.headers, "X-Request-ID": "req-approve-1"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "APPROVED"
    assert response.json()["decision"]["decision"] == "approved"
    after = await state(sessions, incident_id, proposal_id)
    assert after.incident is IncidentStatus.REMEDIATING
    assert after.proposal is ProposalStatus.APPROVED
    [approval] = after.approvals
    assert approval.decision == "approved"
    async with sessions() as session:
        reviewer = await session.get_one(User, approval.reviewed_by)
    assert reviewer.external_auth_id == commander.sub
    assert approval.proposal_version == 1
    assert approval.comment == "Errors began with 1.4.2"
    assert approval.request_id == "req-approve-1"
    assert approval.requested_at is not None
    assert approval.reviewed_at is not None
    assert "remediation.approved" in after.audit
    assert "incident.remediation_approved" in after.events


async def test_rejecting_moves_the_incident_to_rejected(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession], factory: TokenFactory
) -> None:
    commander = Caller(factory, new_org(), "incident-commander")
    incident_id, proposal_id = await awaiting_approval(client, sessions, commander)

    response = await client.post(
        f"/api/v1/proposals/{proposal_id}/reject",
        json={"version": 1, "comment": "Rolling forward instead"},
        headers=commander.headers,
    )

    assert response.status_code == 200, response.text
    after = await state(sessions, incident_id, proposal_id)
    assert after.incident is IncidentStatus.REJECTED
    assert after.proposal is ProposalStatus.REJECTED
    assert "remediation.rejected" in after.audit


@pytest.mark.parametrize("role", ["viewer", "operator"])
async def test_only_approvers_decide(
    client: httpx.AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    factory: TokenFactory,
    role: str,
) -> None:
    owner = Caller(factory, new_org(), "incident-commander")
    incident_id, proposal_id = await awaiting_approval(client, sessions, owner)

    for decision in ("approve", "reject"):
        response = await client.post(
            f"/api/v1/proposals/{proposal_id}/{decision}",
            json={"version": 1},
            headers=Caller(factory, owner.org, role).headers,
        )
        assert response.status_code == 403

    assert (await state(sessions, incident_id, proposal_id)).proposal is ProposalStatus.PENDING


async def test_administrators_may_approve(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession], factory: TokenFactory
) -> None:
    admin = Caller(factory, new_org(), "administrator")
    _, proposal_id = await awaiting_approval(client, sessions, admin)

    response = await client.post(
        f"/api/v1/proposals/{proposal_id}/approve", json={"version": 1}, headers=admin.headers
    )

    assert response.status_code == 200


async def test_a_changed_proposal_needs_a_new_review(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession], factory: TokenFactory
) -> None:
    commander = Caller(factory, new_org(), "incident-commander")
    incident_id, proposal_id = await awaiting_approval(client, sessions, commander)
    async with sessions() as session:
        proposal = await session.get_one(RemediationProposal, uuid.UUID(proposal_id))
        proposal.parameters = {**proposal.parameters, "to_revision": 5}
        proposal.version = 2
        await session.commit()

    response = await client.post(
        f"/api/v1/proposals/{proposal_id}/approve", json={"version": 1}, headers=commander.headers
    )

    assert response.status_code == 409
    assert "changed" in response.json()["detail"]
    assert (await state(sessions, incident_id, proposal_id)).proposal is ProposalStatus.PENDING


async def test_an_expired_proposal_cannot_be_approved(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession], factory: TokenFactory
) -> None:
    commander = Caller(factory, new_org(), "incident-commander")
    incident_id, proposal_id = await awaiting_approval(
        client, sessions, commander, expires_in=-timedelta(minutes=1)
    )

    response = await client.post(
        f"/api/v1/proposals/{proposal_id}/approve", json={"version": 1}, headers=commander.headers
    )

    assert response.status_code == 409
    assert "expired" in response.json()["detail"]
    after = await state(sessions, incident_id, proposal_id)
    assert after.proposal is ProposalStatus.EXPIRED
    assert after.incident is IncidentStatus.AWAITING_APPROVAL


async def test_a_decided_proposal_cannot_be_decided_again(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession], factory: TokenFactory
) -> None:
    commander = Caller(factory, new_org(), "incident-commander")
    _, proposal_id = await awaiting_approval(client, sessions, commander)
    url = f"/api/v1/proposals/{proposal_id}"

    await client.post(f"{url}/reject", json={"version": 1}, headers=commander.headers)
    again = await client.post(f"{url}/approve", json={"version": 1}, headers=commander.headers)

    assert again.status_code == 409


async def test_concurrent_approvals_record_one_decision(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession], factory: TokenFactory
) -> None:
    commander = Caller(factory, new_org(), "incident-commander")
    incident_id, proposal_id = await awaiting_approval(client, sessions, commander)

    responses = await asyncio.gather(
        *(
            client.post(
                f"/api/v1/proposals/{proposal_id}/approve",
                json={"version": 1},
                headers=Caller(factory, commander.org, "incident-commander").headers,
            )
            for _ in range(4)
        )
    )

    assert sorted(r.status_code for r in responses) == [200, 409, 409, 409]
    assert len((await state(sessions, incident_id, proposal_id)).approvals) == 1


async def test_other_organizations_get_404(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession], factory: TokenFactory
) -> None:
    _, proposal_id = await awaiting_approval(
        client, sessions, Caller(factory, new_org(), "incident-commander")
    )
    outsider = Caller(factory, new_org(), "administrator")

    for path in ("approve", "reject"):
        response = await client.post(
            f"/api/v1/proposals/{proposal_id}/{path}", json={"version": 1}, headers=outsider.headers
        )
        assert response.status_code == 404
    assert (
        await client.get(f"/api/v1/proposals/{proposal_id}", headers=outsider.headers)
    ).status_code == 404


async def test_the_proposal_shows_its_decision(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession], factory: TokenFactory
) -> None:
    commander = Caller(factory, new_org(), "incident-commander")
    _, proposal_id = await awaiting_approval(client, sessions, commander)
    viewer = Caller(factory, commander.org, "viewer")

    before = await client.get(f"/api/v1/proposals/{proposal_id}", headers=viewer.headers)
    await client.post(
        f"/api/v1/proposals/{proposal_id}/approve",
        json={"version": 1, "comment": "go"},
        headers=commander.headers,
    )
    after = await client.get(f"/api/v1/proposals/{proposal_id}", headers=viewer.headers)

    assert before.json()["decision"] is None
    assert after.json()["decision"]["comment"] == "go"
    assert after.json()["decision"]["reviewer_name"]
