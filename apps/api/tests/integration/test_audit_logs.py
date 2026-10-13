"""Audit trail: automatic records for mutations, domain events, and the read API."""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

import httpx
import pytest
import sqlalchemy as sa
from asgi_lifespan import LifespanManager
from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.audit.service import record
from opspilot_api.auth.dependencies import CurrentPrincipal, get_token_verifier
from opspilot_api.auth.tokens import TokenVerifier
from opspilot_api.config import Settings
from opspilot_api.db.session import get_session
from opspilot_api.main import create_app
from opspilot_api.redaction import REDACTED
from tests.support.tokens import AUDIENCE, ISSUER, TokenFactory

pytestmark = pytest.mark.integration

probe = APIRouter(prefix="/probe")


@probe.post("/things")
async def create_thing(principal: CurrentPrincipal) -> dict[str, str]:
    return {"ok": "yes"}


@probe.post("/things/{thing_id}/approve")
async def approve_thing(
    thing_id: str,
    principal: CurrentPrincipal,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    await record(
        session,
        principal=principal,
        action="thing.approved",
        resource_type="thing",
        resource_id=thing_id,
        metadata={"comment": "looks good", "api_key": "sk-live-123"},
    )
    await session.commit()
    return {"ok": "yes"}


@probe.post("/anonymous")
async def anonymous() -> dict[str, str]:
    return {"ok": "yes"}


@pytest.fixture
def factory() -> TokenFactory:
    return TokenFactory()


@pytest.fixture
async def client(
    migrated_database_url: str, factory: TokenFactory
) -> AsyncIterator[httpx.AsyncClient]:
    async def resolve(_token: str) -> Any:
        return factory.public_key

    app: FastAPI = create_app(
        Settings(
            app_env="test",
            database_url=migrated_database_url,
            redis_url="redis://unused:6379/0",
            jwt_issuer=ISSUER,
            jwt_audience=AUDIENCE,
        )
    )
    app.include_router(probe)
    verifier = TokenVerifier(issuer=ISSUER, audience=AUDIENCE, key_resolver=resolve)
    app.dependency_overrides[get_token_verifier] = lambda: verifier
    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app, client=("203.0.113.7", 50000))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.fixture
def engine(migrated_database_url: str) -> Any:
    eng = sa.create_engine(migrated_database_url)
    yield eng
    eng.dispose()


class Caller:
    def __init__(self, factory: TokenFactory, org: str, *roles: str) -> None:
        self.org = org
        self.sub = uuid.uuid4().hex
        token = factory.token(sub=self.sub, organization=org, realm_access={"roles": list(roles)})
        self.headers = {"Authorization": f"Bearer {token}"}


def new_org() -> str:
    return f"org-{uuid.uuid4().hex[:10]}"


def rows(engine: sa.Engine, org: str) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        result = conn.execute(
            sa.text(
                "SELECT a.* FROM audit_logs a JOIN organizations o ON o.id = a.organization_id"
                " WHERE o.slug = :org ORDER BY a.created_at, a.id"
            ),
            {"org": org},
        )
        return [dict(r._mapping) for r in result]


async def test_first_login_is_audited(
    client: httpx.AsyncClient, factory: TokenFactory, engine: sa.Engine
) -> None:
    caller = Caller(factory, new_org(), "viewer")

    await client.get("/api/v1/me", headers=caller.headers)
    await client.get("/api/v1/me", headers=caller.headers)

    provisioned = [r for r in rows(engine, caller.org) if r["action"] == "user.provisioned"]
    assert len(provisioned) == 1
    assert provisioned[0]["actor_type"] == "system"


async def test_every_authenticated_mutation_is_audited(
    client: httpx.AsyncClient, factory: TokenFactory, engine: sa.Engine
) -> None:
    caller = Caller(factory, new_org(), "operator")

    response = await client.post(
        "/probe/things", headers={**caller.headers, "X-Request-ID": "req-audit-1"}
    )

    assert response.status_code == 200
    entry = next(r for r in rows(engine, caller.org) if r["action"] == "http.post")
    assert entry["actor_type"] == "user"
    assert entry["resource_type"] == "http_request"
    assert entry["resource_id"] == "/probe/things"
    assert entry["request_id"] == "req-audit-1"
    assert str(entry["ip_address"]) == "203.0.113.7"
    assert entry["metadata_json"] == {"method": "POST", "status_code": 200}


async def test_reads_are_not_audited(
    client: httpx.AsyncClient, factory: TokenFactory, engine: sa.Engine
) -> None:
    caller = Caller(factory, new_org(), "viewer")

    await client.get("/api/v1/me", headers=caller.headers)

    assert [r["action"] for r in rows(engine, caller.org)] == ["user.provisioned"]


async def test_unauthenticated_mutation_writes_no_audit_row(
    client: httpx.AsyncClient, engine: sa.Engine
) -> None:
    with engine.connect() as conn:
        before = conn.execute(sa.text("SELECT count(*) FROM audit_logs")).scalar_one()

    response = await client.post("/probe/anonymous")

    with engine.connect() as conn:
        after = conn.execute(sa.text("SELECT count(*) FROM audit_logs")).scalar_one()
    assert response.status_code == 200
    assert after == before


async def test_domain_event_is_recorded_with_redacted_metadata(
    client: httpx.AsyncClient, factory: TokenFactory, engine: sa.Engine
) -> None:
    caller = Caller(factory, new_org(), "incident-commander")

    await client.post("/probe/things/t-42/approve", headers=caller.headers)

    entry = next(r for r in rows(engine, caller.org) if r["action"] == "thing.approved")
    assert entry["resource_id"] == "t-42"
    assert entry["metadata_json"] == {"comment": "looks good", "api_key": REDACTED}


@pytest.mark.parametrize("role", ["viewer", "operator"])
async def test_reading_audit_logs_requires_permission(
    client: httpx.AsyncClient, factory: TokenFactory, role: str
) -> None:
    response = await client.get(
        "/api/v1/audit-logs", headers=Caller(factory, new_org(), role).headers
    )

    assert response.status_code == 403


async def test_audit_logs_only_show_own_organization(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    mine, theirs = (
        Caller(factory, new_org(), "administrator"),
        Caller(factory, new_org(), "operator"),
    )
    await client.post("/probe/things", headers=theirs.headers)

    response = await client.get("/api/v1/audit-logs", headers=mine.headers)

    assert response.status_code == 200
    actor_ids = {item["actor_id"] for item in response.json()["items"]}
    assert all(theirs.sub not in actor for actor in actor_ids)
    assert response.json()["items"][0]["action"] == "user.provisioned"


async def test_audit_logs_filter_by_action_and_paginate(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    admin = Caller(factory, new_org(), "administrator")
    for _ in range(5):
        await client.post("/probe/things", headers=admin.headers)

    first = await client.get(
        "/api/v1/audit-logs", params={"action": "http.post", "limit": 2}, headers=admin.headers
    )
    second = await client.get(
        "/api/v1/audit-logs",
        params={"action": "http.post", "limit": 2, "cursor": first.json()["next_cursor"]},
        headers=admin.headers,
    )
    third = await client.get(
        "/api/v1/audit-logs",
        params={"action": "http.post", "limit": 2, "cursor": second.json()["next_cursor"]},
        headers=admin.headers,
    )

    pages = [first.json(), second.json(), third.json()]
    ids = [item["id"] for page in pages for item in page["items"]]
    assert [len(page["items"]) for page in pages] == [2, 2, 1]
    assert len(set(ids)) == 5
    assert third.json()["next_cursor"] is None
    assert all(item["action"] == "http.post" for page in pages for item in page["items"])
    created = [item["created_at"] for page in pages for item in page["items"]]
    assert created == sorted(created, reverse=True)


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 501}, {"cursor": "not-a-cursor"}],
    ids=["limit-too-small", "limit-too-large", "bad-cursor"],
)
async def test_audit_logs_reject_bad_parameters(
    client: httpx.AsyncClient, factory: TokenFactory, params: dict[str, Any]
) -> None:
    admin = Caller(factory, new_org(), "administrator")

    response = await client.get("/api/v1/audit-logs", params=params, headers=admin.headers)

    assert response.status_code == 422
