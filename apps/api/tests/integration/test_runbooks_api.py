"""Runbook management: create, read, version, archive, permissions, tenancy, audit."""

from collections.abc import AsyncIterator

import httpx
import pytest
import sqlalchemy as sa

from tests.support.app import Caller, api_client, new_org
from tests.support.tokens import TokenFactory

pytestmark = pytest.mark.integration


def runbook(
    title: str = "Checkout high error rate", version: int = 1, body: str = "Checkout fails."
) -> str:
    return f"""---
title: {title}
services: [checkout, storefront]
owner: shop-team
version: {version}
---

# {title}

## Scope

{body}

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


async def create(
    client: httpx.AsyncClient, caller: Caller, content: str, **extra: str
) -> httpx.Response:
    return await client.post(
        "/api/v1/runbooks", json={"content": content, **extra}, headers=caller.headers
    )


async def test_operator_creates_and_viewer_reads_a_runbook(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    operator = Caller(factory, new_org(), "operator")

    created = await create(client, operator, runbook(), source_url="https://example.com/rb")
    assert created.status_code == 201, created.text
    body = created.json()
    viewer = Caller(factory, operator.org, "viewer")
    listed = await client.get("/api/v1/runbooks", headers=viewer.headers)
    detail = await client.get(f"/api/v1/runbooks/{body['id']}", headers=viewer.headers)

    assert (body["slug"], body["version"], body["status"]) == (
        "checkout-high-error-rate",
        1,
        "active",
    )
    assert body["services"] == ["checkout", "storefront"]
    assert [r["slug"] for r in listed.json()["items"]] == ["checkout-high-error-rate"]
    assert "content" not in listed.json()["items"][0]
    assert detail.json()["content"].startswith("---")
    assert [s["heading"] for s in detail.json()["sections"]] == ["Scope", "Safe actions"]


async def test_invalid_documents_are_rejected(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    response = await create(client, Caller(factory, new_org(), "operator"), "# no front matter")

    assert response.status_code == 422
    assert "front matter" in response.text


async def test_duplicate_slugs_conflict(client: httpx.AsyncClient, factory: TokenFactory) -> None:
    operator = Caller(factory, new_org(), "operator")
    await create(client, operator, runbook())

    assert (await create(client, operator, runbook())).status_code == 409


async def test_updating_content_creates_a_new_version(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    operator = Caller(factory, new_org(), "operator")
    rb = (await create(client, operator, runbook())).json()

    same = await client.put(
        f"/api/v1/runbooks/{rb['id']}", json={"content": runbook()}, headers=operator.headers
    )
    changed = await client.put(
        f"/api/v1/runbooks/{rb['id']}",
        json={"content": runbook(body="Checkout fails badly.")},
        headers=operator.headers,
    )

    assert same.json()["version"] == 1
    assert changed.status_code == 200, changed.text
    assert changed.json()["version"] == 2
    assert "badly" in changed.json()["content"]


async def test_archived_runbooks_leave_the_default_list(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    operator = Caller(factory, new_org(), "operator")
    rb = (await create(client, operator, runbook())).json()

    archived = await client.post(f"/api/v1/runbooks/{rb['id']}/archive", headers=operator.headers)
    listed = await client.get("/api/v1/runbooks", headers=operator.headers)
    everything = await client.get("/api/v1/runbooks?status=all", headers=operator.headers)

    assert archived.json()["status"] == "archived"
    assert listed.json()["items"] == []
    assert len(everything.json()["items"]) == 1


async def test_viewers_cannot_change_runbooks(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    operator = Caller(factory, new_org(), "operator")
    rb = (await create(client, operator, runbook())).json()
    viewer = Caller(factory, operator.org, "viewer")

    assert (await create(client, viewer, runbook("Other"))).status_code == 403
    put = await client.put(
        f"/api/v1/runbooks/{rb['id']}", json={"content": runbook()}, headers=viewer.headers
    )
    archive = await client.post(f"/api/v1/runbooks/{rb['id']}/archive", headers=viewer.headers)
    assert (put.status_code, archive.status_code) == (403, 403)


async def test_other_organizations_see_nothing(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    rb = (await create(client, Caller(factory, new_org(), "operator"), runbook())).json()
    outsider = Caller(factory, new_org(), "administrator")

    assert (
        await client.get(f"/api/v1/runbooks/{rb['id']}", headers=outsider.headers)
    ).status_code == 404
    assert (await client.get("/api/v1/runbooks", headers=outsider.headers)).json()["items"] == []


async def test_changes_are_audited(
    client: httpx.AsyncClient, factory: TokenFactory, migrated_database_url: str
) -> None:
    operator = Caller(factory, new_org(), "operator")
    rb = (await create(client, operator, runbook())).json()
    await client.put(
        f"/api/v1/runbooks/{rb['id']}",
        json={"content": runbook(body="v2")},
        headers=operator.headers,
    )
    await client.post(f"/api/v1/runbooks/{rb['id']}/archive", headers=operator.headers)

    engine = sa.create_engine(migrated_database_url)
    with engine.connect() as conn:
        actions = (
            conn.execute(
                sa.text(
                    "SELECT action FROM audit_logs WHERE resource_id = :id ORDER BY created_at"
                ),
                {"id": rb["id"]},
            )
            .scalars()
            .all()
        )
    engine.dispose()
    assert actions == ["runbook.created", "runbook.updated", "runbook.archived"]


async def test_runbooks_require_authentication(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/runbooks")).status_code == 401
