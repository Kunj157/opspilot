"""Idempotency-Key on every mutating endpoint (plan §14): a retry replays, it never redoes."""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opspilot_api.db.models import (
    AuditLog,
    Incident,
    IncidentStatus,
    Organization,
    RemediationAction,
    RemediationProposal,
)
from tests.support.app import Caller, api_client, new_org
from tests.support.tokens import TokenFactory

pytestmark = pytest.mark.integration

Request = tuple[str, str, dict[str, object] | None]
Setup = Callable[[httpx.AsyncClient, Caller, async_sessionmaker[AsyncSession]], Awaitable[Request]]


@pytest.fixture
def factory() -> TokenFactory:
    return TokenFactory()


@pytest.fixture
async def client(
    migrated_database_url: str, factory: TokenFactory
) -> AsyncIterator[httpx.AsyncClient]:
    async with api_client(migrated_database_url, factory) as c:
        yield c


async def incident(
    client: httpx.AsyncClient,
    caller: Caller,
    sessions: async_sessionmaker[AsyncSession],
    status: IncidentStatus | None = None,
) -> tuple[str, int]:
    created = await client.post(
        "/api/v1/incidents",
        json={"title": "Checkout errors", "severity": "high"},
        headers=caller.headers,
    )
    incident_id = created.json()["id"]
    if status is None:
        return incident_id, created.json()["version"]
    async with sessions() as session:
        row = await session.get_one(Incident, uuid.UUID(incident_id))
        row.status = status
        await session.commit()
        return incident_id, row.version


async def proposal(
    client: httpx.AsyncClient,
    caller: Caller,
    sessions: async_sessionmaker[AsyncSession],
    expires_in: timedelta = timedelta(minutes=30),
) -> str:
    incident_id, _ = await incident(client, caller, sessions, IncidentStatus.AWAITING_APPROVAL)
    async with sessions() as session:
        row = await session.get_one(Incident, uuid.UUID(incident_id))
        created = RemediationProposal(
            organization_id=row.organization_id,
            incident_id=row.id,
            action_type=RemediationAction.ROLLBACK_DEPLOYMENT,
            description="Roll back checkout to revision 6",
            parameters={"namespace": "demo", "deployment": "checkout", "to_revision": 6},
            risk_level="medium",
            verification_plan={"window_minutes": 3},
            expires_at=datetime.now(UTC) + expires_in,
        )
        session.add(created)
        await session.commit()
        return str(created.id)


async def service(client: httpx.AsyncClient, caller: Caller) -> str:
    slug = f"svc-{uuid.uuid4().hex[:8]}"
    created = await client.post(
        "/api/v1/services", json={"name": slug, "slug": slug}, headers=caller.headers
    )
    return str(created.json()["id"])


async def patch_incident(
    c: httpx.AsyncClient, u: Caller, s: async_sessionmaker[AsyncSession]
) -> Request:
    incident_id, version = await incident(c, u, s)
    return "PATCH", f"/api/v1/incidents/{incident_id}", {"title": "Renamed", "version": version}


def transition(action: str, status: IncidentStatus | None = None) -> Setup:
    async def setup(
        c: httpx.AsyncClient, u: Caller, s: async_sessionmaker[AsyncSession]
    ) -> Request:
        incident_id, version = await incident(c, u, s, status)
        return "POST", f"/api/v1/incidents/{incident_id}/{action}", {"version": version}

    return setup


def decision(action: str) -> Setup:
    async def setup(
        c: httpx.AsyncClient, u: Caller, s: async_sessionmaker[AsyncSession]
    ) -> Request:
        return "POST", f"/api/v1/proposals/{await proposal(c, u, s)}/{action}", {"version": 1}

    return setup


async def patch_service(
    c: httpx.AsyncClient, u: Caller, _: async_sessionmaker[AsyncSession]
) -> Request:
    return "PATCH", f"/api/v1/services/{await service(c, u)}", {"name": "Renamed"}


async def put_dependencies(
    c: httpx.AsyncClient, u: Caller, _: async_sessionmaker[AsyncSession]
) -> Request:
    source, target = await service(c, u), await service(c, u)
    return "PUT", f"/api/v1/services/{source}/dependencies", {"target_ids": [target]}


ENDPOINTS: dict[str, Setup] = {
    "update incident": patch_incident,
    "acknowledge": transition("acknowledge"),
    "investigate": transition("investigate"),
    "resolve": transition("resolve", IncidentStatus.MONITORING),
    "approve proposal": decision("approve"),
    "reject proposal": decision("reject"),
    "update service": patch_service,
    "replace dependencies": put_dependencies,
}


async def work_done(sessions: async_sessionmaker[AsyncSession], org: str) -> int:
    """Domain audit records of `org`: one per action, never written by a replay."""
    async with sessions() as session:
        return int(
            await session.scalar(
                sa.select(sa.func.count())
                .select_from(AuditLog)
                .join(Organization, Organization.id == AuditLog.organization_id)
                .where(Organization.slug == org, ~AuditLog.action.startswith("http."))
            )
            or 0
        )


@pytest.mark.parametrize("endpoint", ENDPOINTS)
async def test_a_retry_with_the_same_key_replays_without_redoing_the_work(
    client: httpx.AsyncClient,
    factory: TokenFactory,
    sessions: async_sessionmaker[AsyncSession],
    endpoint: str,
) -> None:
    caller = Caller(factory, new_org(), "administrator")
    method, path, body = await ENDPOINTS[endpoint](client, caller, sessions)
    headers = {**caller.headers, "Idempotency-Key": f"retry-{endpoint.replace(' ', '-')}"}

    first = await client.request(method, path, json=body, headers=headers)
    done = await work_done(sessions, caller.org)
    second = await client.request(method, path, json=body, headers=headers)

    assert first.status_code < 300, first.text
    assert second.status_code == first.status_code
    assert second.json() == first.json()
    assert second.headers["Idempotency-Replayed"] == "true"
    assert "Idempotency-Replayed" not in first.headers
    assert await work_done(sessions, caller.org) == done


async def test_without_a_key_a_retried_transition_fails_on_the_version(
    client: httpx.AsyncClient, factory: TokenFactory, sessions: async_sessionmaker[AsyncSession]
) -> None:
    caller = Caller(factory, new_org(), "administrator")
    method, path, body = await transition("acknowledge")(client, caller, sessions)

    first = await client.request(method, path, json=body, headers=caller.headers)
    second = await client.request(method, path, json=body, headers=caller.headers)

    assert (first.status_code, second.status_code) == (200, 409)


async def test_a_key_cannot_be_reused_on_another_endpoint(
    client: httpx.AsyncClient, factory: TokenFactory, sessions: async_sessionmaker[AsyncSession]
) -> None:
    caller = Caller(factory, new_org(), "administrator")
    headers = {**caller.headers, "Idempotency-Key": "one-use"}
    incident_id, version = await incident(client, caller, sessions)
    await client.post(
        f"/api/v1/incidents/{incident_id}/acknowledge", json={"version": version}, headers=headers
    )

    response = await client.post(
        f"/api/v1/incidents/{incident_id}/investigate", json={"version": version}, headers=headers
    )

    assert response.status_code == 422
    assert "Idempotency-Key" in response.text


async def test_an_expired_proposal_replays_its_conflict(
    client: httpx.AsyncClient, factory: TokenFactory, sessions: async_sessionmaker[AsyncSession]
) -> None:
    caller = Caller(factory, new_org(), "incident-commander")
    proposal_id = await proposal(client, caller, sessions, expires_in=timedelta(minutes=-1))
    headers = {**caller.headers, "Idempotency-Key": "late"}
    path = f"/api/v1/proposals/{proposal_id}/approve"

    first = await client.post(path, json={"version": 1}, headers=headers)
    second = await client.post(path, json={"version": 1}, headers=headers)

    assert first.status_code == second.status_code == 409
    assert second.json() == first.json()
    assert second.headers["Idempotency-Replayed"] == "true"


async def test_a_rejected_request_does_not_burn_the_key(
    client: httpx.AsyncClient, factory: TokenFactory, sessions: async_sessionmaker[AsyncSession]
) -> None:
    caller = Caller(factory, new_org(), "administrator")
    incident_id, version = await incident(client, caller, sessions)
    headers = {**caller.headers, "Idempotency-Key": "stale-then-fixed"}
    path = f"/api/v1/incidents/{incident_id}"

    stale = await client.patch(path, json={"title": "X", "version": version + 5}, headers=headers)
    retry = await client.patch(path, json={"title": "X", "version": version + 5}, headers=headers)

    assert (stale.status_code, retry.status_code) == (409, 409)
    assert "Idempotency-Replayed" not in retry.headers
