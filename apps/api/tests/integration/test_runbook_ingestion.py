"""Ingestion on create and update, idempotence, and reindexing."""

from collections.abc import AsyncIterator

import httpx
import pytest
import sqlalchemy as sa

from tests.support.app import Caller, api_client, new_org
from tests.support.tokens import TokenFactory

pytestmark = pytest.mark.integration

RUNBOOK = """---
title: Checkout high error rate
services: [checkout]
version: 1
---

## Symptoms

{symptoms}

## Safe actions

Roll back checkout.
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


def chunks(url: str, runbook_id: str) -> list[tuple[str, str, int, str]]:
    engine = sa.create_engine(url)
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT id::text, heading, version, vector_dims(embedding)::text"
                " FROM runbook_chunks WHERE runbook_id = :id ORDER BY ordinal"
            ),
            {"id": runbook_id},
        ).all()
    engine.dispose()
    return [(r[0], r[1], r[2], r[3]) for r in rows]


async def test_creating_a_runbook_embeds_its_sections(
    client: httpx.AsyncClient, factory: TokenFactory, migrated_database_url: str
) -> None:
    operator = Caller(factory, new_org(), "operator")

    rb = (
        await client.post(
            "/api/v1/runbooks",
            json={"content": RUNBOOK.format(symptoms="Checkout fails.")},
            headers=operator.headers,
        )
    ).json()

    rows = chunks(migrated_database_url, rb["id"])
    assert [(r[1], r[2], r[3]) for r in rows] == [
        ("Symptoms", 1, "384"),
        ("Safe actions", 1, "384"),
    ]


async def test_a_new_version_replaces_the_chunks_and_unchanged_text_keeps_them(
    client: httpx.AsyncClient, factory: TokenFactory, migrated_database_url: str
) -> None:
    operator = Caller(factory, new_org(), "operator")
    rb = (
        await client.post(
            "/api/v1/runbooks",
            json={"content": RUNBOOK.format(symptoms="Checkout fails.")},
            headers=operator.headers,
        )
    ).json()
    before = chunks(migrated_database_url, rb["id"])

    await client.put(
        f"/api/v1/runbooks/{rb['id']}",
        json={"content": RUNBOOK.format(symptoms="Checkout fails.")},
        headers=operator.headers,
    )
    unchanged = chunks(migrated_database_url, rb["id"])
    await client.put(
        f"/api/v1/runbooks/{rb['id']}",
        json={"content": RUNBOOK.format(symptoms="Checkout fails with 502.")},
        headers=operator.headers,
    )
    after = chunks(migrated_database_url, rb["id"])

    assert unchanged == before
    assert {r[2] for r in after} == {2}
    assert not {r[0] for r in after} & {r[0] for r in before}


async def test_reindex_rebuilds_every_active_runbook(
    client: httpx.AsyncClient, factory: TokenFactory, migrated_database_url: str
) -> None:
    operator = Caller(factory, new_org(), "operator")
    rb = (
        await client.post(
            "/api/v1/runbooks",
            json={"content": RUNBOOK.format(symptoms="Checkout fails.")},
            headers=operator.headers,
        )
    ).json()
    before = {r[0] for r in chunks(migrated_database_url, rb["id"])}

    response = await client.post("/api/v1/runbooks/reindex", headers=operator.headers)

    assert response.status_code == 200, response.text
    assert response.json() == {"reindexed": 1, "chunks": 2}
    assert not before & {r[0] for r in chunks(migrated_database_url, rb["id"])}


async def test_viewers_cannot_reindex(client: httpx.AsyncClient, factory: TokenFactory) -> None:
    response = await client.post(
        "/api/v1/runbooks/reindex", headers=Caller(factory, new_org(), "viewer").headers
    )

    assert response.status_code == 403
