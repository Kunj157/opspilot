"""Trust boundaries (plan §21.5): SQL injection, stored XSS payloads, and SSRF."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opspilot_api.db.models import (
    ActorType,
    AuditLog,
    Incident,
    IncidentEvent,
    IncidentStatus,
    Postmortem,
)
from tests.support.app import Caller, api_client, new_org
from tests.support.tokens import TokenFactory

pytestmark = pytest.mark.integration

SQL_INJECTION = [
    "' OR '1'='1",
    "x'; DROP TABLE incidents; --",
    "1 UNION SELECT id, slug FROM organizations --",
    "\\'; SELECT pg_sleep(5); --",
    "%' OR 1=1 --",
    "admin'--",
]
XSS = [
    "<script>alert(1)</script>",
    '<img src=x onerror="alert(1)">',
    "<svg/onload=alert(1)>",
    "javascript:alert(1)",
    '"><iframe src=//evil.example>',
]
RUNBOOK = """---
title: Checkout errors
services: [checkout]
owner: shop-team
version: 1
---

# Checkout errors

## Scope

Checkout requests fail with errors.

## Safe actions

Roll back the latest release.
"""


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
async def victim(client: httpx.AsyncClient, factory: TokenFactory) -> Caller:
    """Another organization with data an injection would try to reach."""
    caller = Caller(factory, new_org(), "administrator")
    await client.post(
        "/api/v1/incidents",
        json={"title": "Victim incident", "severity": "high"},
        headers=caller.headers,
    )
    await client.post("/api/v1/runbooks", json={"content": RUNBOOK}, headers=caller.headers)
    return caller


async def table_rows(sessions: async_sessionmaker[AsyncSession], table: str) -> int:
    async with sessions() as session:
        return int(await session.scalar(sa.text(f"SELECT count(*) FROM {table}")) or 0)


# --- SQL injection: every filter and search parameter is bound, never interpolated ---


@pytest.mark.parametrize(
    "param",
    ["status", "severity", "source", "service_id", "assigned_user_id", "since", "until", "cursor"],
)
@pytest.mark.parametrize("payload", SQL_INJECTION)
async def test_typed_incident_filters_reject_injection(
    client: httpx.AsyncClient, factory: TokenFactory, victim: Caller, param: str, payload: str
) -> None:
    caller = Caller(factory, new_org(), "viewer")

    response = await client.get(
        "/api/v1/incidents", params={param: payload}, headers=caller.headers
    )

    assert response.status_code == 422


@pytest.mark.parametrize("param", ["action", "actor_id", "resource_type"])
@pytest.mark.parametrize("payload", SQL_INJECTION)
async def test_audit_filters_treat_injection_as_a_literal(
    client: httpx.AsyncClient,
    factory: TokenFactory,
    sessions: async_sessionmaker[AsyncSession],
    victim: Caller,
    param: str,
    payload: str,
) -> None:
    admin = Caller(factory, new_org(), "administrator")
    await client.post(
        "/api/v1/incidents", json={"title": "Mine", "severity": "low"}, headers=admin.headers
    )
    rows_before = await table_rows(sessions, "audit_logs")

    response = await client.get(
        "/api/v1/audit-logs", params={param: payload}, headers=admin.headers
    )
    unfiltered = await client.get("/api/v1/audit-logs", headers=admin.headers)

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert unfiltered.json()["items"], "the organization's own records are still there"
    assert victim.sub not in unfiltered.text
    assert await table_rows(sessions, "audit_logs") >= rows_before


@pytest.mark.parametrize("payload", SQL_INJECTION)
async def test_runbook_search_treats_injection_as_text(
    client: httpx.AsyncClient,
    factory: TokenFactory,
    sessions: async_sessionmaker[AsyncSession],
    victim: Caller,
    payload: str,
) -> None:
    caller = Caller(factory, new_org(), "operator")
    own = await client.post("/api/v1/runbooks", json={"content": RUNBOOK}, headers=caller.headers)

    by_query = await client.get(
        "/api/v1/runbooks/search", params={"q": payload}, headers=caller.headers
    )
    by_service = await client.get(
        "/api/v1/runbooks/search",
        params={"q": "checkout errors", "service": payload[:63]},
        headers=caller.headers,
    )

    control = await client.get(
        "/api/v1/runbooks/search",
        params={"q": "checkout errors", "service": "checkout"},
        headers=caller.headers,
    )

    assert by_query.status_code == by_service.status_code == control.status_code == 200
    assert by_service.json()["items"] == [], "the payload is matched as a service name"
    assert control.json()["items"], "the search still works"
    for response in (by_query, by_service):
        assert {h["runbook_id"] for h in response.json()["items"]} <= {own.json()["id"]}
    assert await table_rows(sessions, "incidents") > 0


# --- Stored XSS: payloads are data; the API returns them verbatim as JSON ---


@pytest.mark.parametrize("payload", XSS)
async def test_incident_text_is_returned_verbatim_as_json(
    client: httpx.AsyncClient,
    factory: TokenFactory,
    sessions: async_sessionmaker[AsyncSession],
    payload: str,
) -> None:
    caller = Caller(factory, new_org(), "administrator")
    created = await client.post(
        "/api/v1/incidents",
        json={"title": payload, "description": payload, "severity": "low"},
        headers=caller.headers,
    )
    incident_id = uuid.UUID(created.json()["id"])
    async with sessions() as session:
        incident = await session.get_one(Incident, incident_id)
        incident.status = IncidentStatus.RESOLVED
        session.add_all(
            [
                IncidentEvent(
                    organization_id=incident.organization_id,
                    incident_id=incident.id,
                    event_type="note",
                    actor_type=ActorType.AGENT,
                    actor_id="agent:test",
                    title=payload,
                    description=payload,
                ),
                Postmortem(
                    organization_id=incident.organization_id,
                    incident_id=incident.id,
                    status="ready",
                    content={"summary": payload, "timeline": [payload]},
                ),
            ]
        )
        await session.commit()

    responses = [
        await client.get(f"/api/v1/incidents/{incident_id}", headers=caller.headers),
        await client.get("/api/v1/incidents", headers=caller.headers),
        await client.get(f"/api/v1/incidents/{incident_id}/events", headers=caller.headers),
        await client.get(f"/api/v1/incidents/{incident_id}/postmortem", headers=caller.headers),
    ]

    detail, listing, events, postmortem = (r.json() for r in responses)
    for response in responses:
        assert response.headers["content-type"] == "application/json"
    assert (detail["title"], detail["description"]) == (payload, payload)
    assert listing["items"][0]["title"] == payload
    assert [e["title"] for e in events["items"] if e["event_type"] == "note"] == [payload]
    assert postmortem["content"] == {"summary": payload, "timeline": [payload]}


# --- SSRF: URLs from users are links for people, validated and never fetched ---


@pytest.mark.parametrize(
    "url", ["javascript:alert(1)", "file:///etc/passwd", "data:text/html,<script>", "gopher://x"]
)
async def test_link_fields_accept_only_http_urls(
    client: httpx.AsyncClient, factory: TokenFactory, url: str
) -> None:
    caller = Caller(factory, new_org(), "administrator")

    runbook = await client.post(
        "/api/v1/runbooks", json={"content": RUNBOOK, "source_url": url}, headers=caller.headers
    )
    service = await client.post(
        "/api/v1/services",
        json={"name": "Svc", "slug": "svc", "repository_url": url},
        headers=caller.headers,
    )

    assert runbook.status_code == service.status_code == 422


async def test_user_supplied_urls_are_never_fetched(
    client: httpx.AsyncClient, factory: TokenFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    outbound: list[str] = []

    async def record(_: object, request: httpx.Request) -> httpx.Response:
        outbound.append(str(request.url))
        return httpx.Response(599)

    # The test client uses the ASGI transport; only real network calls land here.
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", record)
    caller = Caller(factory, new_org(), "administrator")
    metadata = "http://169.254.169.254/latest/meta-data/"

    runbook = await client.post(
        "/api/v1/runbooks",
        json={"content": RUNBOOK, "source_url": metadata},
        headers=caller.headers,
    )
    service = await client.post(
        "/api/v1/services",
        json={"name": "Svc", "slug": "svc-ssrf", "repository_url": metadata},
        headers=caller.headers,
    )
    hits = await client.get(
        "/api/v1/runbooks/search", params={"q": "checkout"}, headers=caller.headers
    )

    assert (runbook.status_code, service.status_code, hits.status_code) == (201, 201, 200)
    assert hits.json()["items"][0]["source_url"] == metadata, hits.text
    assert outbound == []


async def test_audit_log_rows_are_never_rewritten_by_filters(
    client: httpx.AsyncClient, factory: TokenFactory, sessions: async_sessionmaker[AsyncSession]
) -> None:
    admin = Caller(factory, new_org(), "administrator")
    await client.get(
        "/api/v1/audit-logs",
        params={"action": "x'; UPDATE audit_logs SET action='pwned'; --"},
        headers=admin.headers,
    )

    async with sessions() as session:
        pwned = await session.scalar(
            sa.select(sa.func.count()).select_from(AuditLog).where(AuditLog.action == "pwned")
        )
    assert pwned == 0
