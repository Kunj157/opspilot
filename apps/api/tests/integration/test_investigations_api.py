"""Starting and reading investigations: permissions, idempotence, tenancy, queue claims."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from opspilot_api.agents.queue import claim
from opspilot_api.db.models import Investigation, InvestigationStatus
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


async def incident(client: httpx.AsyncClient, caller: Caller) -> str:
    response = await client.post(
        "/api/v1/incidents",
        json={"title": "Checkout errors", "severity": "high"},
        headers=caller.headers,
    )
    return str(response.json()["id"])


async def test_operator_starts_an_investigation_once(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    operator = Caller(factory, new_org(), "operator")
    incident_id = await incident(client, operator)

    first = await client.post(
        f"/api/v1/incidents/{incident_id}/investigation", headers=operator.headers
    )
    again = await client.post(
        f"/api/v1/incidents/{incident_id}/investigation", headers=operator.headers
    )
    read = await client.get(
        f"/api/v1/incidents/{incident_id}/investigation",
        headers=Caller(factory, operator.org, "viewer").headers,
    )

    assert first.status_code == 202, first.text
    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]
    assert read.json()["status"] == "queued"


async def test_viewers_cannot_start_investigations(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    operator = Caller(factory, new_org(), "operator")
    incident_id = await incident(client, operator)

    response = await client.post(
        f"/api/v1/incidents/{incident_id}/investigation",
        headers=Caller(factory, operator.org, "viewer").headers,
    )

    assert response.status_code == 403


async def test_other_organizations_get_404_everywhere(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    incident_id = await incident(client, Caller(factory, new_org(), "operator"))
    outsider = Caller(factory, new_org(), "administrator")

    for method, path in [
        ("POST", "investigation"),
        ("GET", "investigation"),
        ("GET", "evidence"),
        ("GET", "agent-runs"),
        ("GET", "proposals"),
    ]:
        response = await client.request(
            method, f"/api/v1/incidents/{incident_id}/{path}", headers=outsider.headers
        )
        assert response.status_code == 404, (method, path)


async def test_empty_lists_before_any_investigation(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    operator = Caller(factory, new_org(), "operator")
    incident_id = await incident(client, operator)

    for path in ("evidence", "agent-runs", "proposals"):
        assert (
            await client.get(f"/api/v1/incidents/{incident_id}/{path}", headers=operator.headers)
        ).json() == {"items": []}
    assert (
        await client.get(f"/api/v1/incidents/{incident_id}/investigation", headers=operator.headers)
    ).status_code == 404


async def test_starting_is_audited(
    client: httpx.AsyncClient, factory: TokenFactory, migrated_database_url: str
) -> None:
    operator = Caller(factory, new_org(), "operator")
    incident_id = await incident(client, operator)
    started = (
        await client.post(
            f"/api/v1/incidents/{incident_id}/investigation", headers=operator.headers
        )
    ).json()

    engine = sa.create_engine(migrated_database_url)
    with engine.connect() as conn:
        action = conn.execute(
            sa.text("SELECT action FROM audit_logs WHERE resource_id = :id"), {"id": started["id"]}
        ).scalar_one()
    engine.dispose()
    assert action == "investigation.requested"


async def test_claims_are_exclusive_and_expired_leases_return(
    client: httpx.AsyncClient, factory: TokenFactory, sessions: async_sessionmaker[AsyncSession]
) -> None:
    operator = Caller(factory, new_org(), "operator")
    incident_id = await incident(client, operator)
    started = (
        await client.post(
            f"/api/v1/incidents/{incident_id}/investigation", headers=operator.headers
        )
    ).json()
    mine = uuid.UUID(started["id"])

    claims = await asyncio.gather(
        *(claim(sessions, timedelta(minutes=5), only=mine) for _ in range(4))
    )
    claimed = [c for c in claims if c is not None]
    assert len(claimed) == 1
    assert claimed[0].status is InvestigationStatus.RUNNING
    assert claimed[0].attempts == 1

    async with sessions() as session:
        await session.execute(
            sa.update(Investigation)
            .where(Investigation.id == mine)
            .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
        await session.commit()
    reclaimed = await claim(sessions, timedelta(minutes=5), only=mine)
    assert reclaimed is not None
    assert reclaimed.attempts == 2
