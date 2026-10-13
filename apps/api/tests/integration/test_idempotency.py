"""Idempotency-Key on create requests (plan §14)."""

import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
import sqlalchemy as sa

from tests.support.app import Caller, api_client, new_org
from tests.support.tokens import TokenFactory

pytestmark = pytest.mark.integration

ENDPOINTS = {
    "services": lambda n: {"name": f"Svc {n}", "slug": f"svc-{n}"},
    "incidents": lambda n: {"title": f"Incident {n}", "severity": "low"},
}


@pytest.fixture
def factory() -> TokenFactory:
    return TokenFactory()


@pytest.fixture
async def client(
    migrated_database_url: str, factory: TokenFactory
) -> AsyncIterator[httpx.AsyncClient]:
    async with api_client(migrated_database_url, factory) as c:
        yield c


def count(database_url: str, table: str, org: str) -> int:
    engine = sa.create_engine(database_url)
    try:
        with engine.connect() as conn:
            return int(
                conn.execute(
                    sa.text(
                        f"SELECT count(*) FROM {table} t JOIN organizations o"
                        " ON o.id = t.organization_id WHERE o.slug = :org"
                    ),
                    {"org": org},
                ).scalar_one()
            )
    finally:
        engine.dispose()


@pytest.mark.parametrize("resource", ENDPOINTS)
async def test_retry_with_the_same_key_replays_the_first_response(
    client: httpx.AsyncClient, factory: TokenFactory, migrated_database_url: str, resource: str
) -> None:
    caller = Caller(factory, new_org(), "operator")
    headers = {**caller.headers, "Idempotency-Key": "create-1"}
    body = ENDPOINTS[resource](1)

    first = await client.post(f"/api/v1/{resource}", json=body, headers=headers)
    second = await client.post(f"/api/v1/{resource}", json=body, headers=headers)

    assert first.status_code == second.status_code == 201
    assert second.json() == first.json()
    assert second.headers["Idempotency-Replayed"] == "true"
    assert "Idempotency-Replayed" not in first.headers
    assert count(migrated_database_url, resource, caller.org) == 1


@pytest.mark.parametrize("resource", ENDPOINTS)
async def test_concurrent_duplicates_create_one_record(
    client: httpx.AsyncClient, factory: TokenFactory, migrated_database_url: str, resource: str
) -> None:
    caller = Caller(factory, new_org(), "operator")
    await client.get("/api/v1/me", headers=caller.headers)  # provision before the race
    headers = {**caller.headers, "Idempotency-Key": "race"}
    body = ENDPOINTS[resource](2)

    responses = await asyncio.gather(
        *(client.post(f"/api/v1/{resource}", json=body, headers=headers) for _ in range(6))
    )

    assert {r.status_code for r in responses} == {201}
    assert len({r.json()["id"] for r in responses}) == 1
    assert count(migrated_database_url, resource, caller.org) == 1


async def test_reusing_a_key_with_a_different_body_is_rejected(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    caller = Caller(factory, new_org(), "operator")
    headers = {**caller.headers, "Idempotency-Key": "reused"}
    await client.post("/api/v1/incidents", json=ENDPOINTS["incidents"](1), headers=headers)

    response = await client.post(
        "/api/v1/incidents", json=ENDPOINTS["incidents"](2), headers=headers
    )

    assert response.status_code == 422
    assert "Idempotency-Key" in response.text


async def test_keys_are_scoped_per_organization(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    body = ENDPOINTS["incidents"](1)
    first = await client.post(
        "/api/v1/incidents",
        json=body,
        headers={**Caller(factory, new_org(), "operator").headers, "Idempotency-Key": "shared"},
    )
    second = await client.post(
        "/api/v1/incidents",
        json=body,
        headers={**Caller(factory, new_org(), "operator").headers, "Idempotency-Key": "shared"},
    )

    assert first.json()["id"] != second.json()["id"]


async def test_without_a_key_each_request_creates(
    client: httpx.AsyncClient, factory: TokenFactory, migrated_database_url: str
) -> None:
    caller = Caller(factory, new_org(), "operator")

    for _ in range(2):
        await client.post(
            "/api/v1/incidents", json=ENDPOINTS["incidents"](1), headers=caller.headers
        )

    assert count(migrated_database_url, "incidents", caller.org) == 2


async def test_a_failed_request_does_not_burn_the_key(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    caller = Caller(factory, new_org(), "operator")
    await client.post(
        "/api/v1/services", json={"name": "A", "slug": "taken"}, headers=caller.headers
    )
    headers = {**caller.headers, "Idempotency-Key": "after-conflict"}
    body = {"name": "B", "slug": "taken"}

    conflict = await client.post("/api/v1/services", json=body, headers=headers)
    retry = await client.post("/api/v1/services", json=body, headers=headers)

    assert (conflict.status_code, retry.status_code) == (409, 409)
    assert "Idempotency-Replayed" not in retry.headers


@pytest.mark.parametrize("key", ["", "x" * 256, "has\nnewline"])
async def test_malformed_keys_are_rejected(
    client: httpx.AsyncClient, factory: TokenFactory, key: str
) -> None:
    caller = Caller(factory, new_org(), "operator")

    response = await client.post(
        "/api/v1/incidents",
        json=ENDPOINTS["incidents"](1),
        headers={**caller.headers, "Idempotency-Key": key},
    )

    assert response.status_code == 422


async def test_expired_keys_can_be_reused(
    client: httpx.AsyncClient, factory: TokenFactory, migrated_database_url: str
) -> None:
    caller = Caller(factory, new_org(), "operator")
    headers = {**caller.headers, "Idempotency-Key": "old"}
    first = await client.post("/api/v1/incidents", json=ENDPOINTS["incidents"](1), headers=headers)
    engine = sa.create_engine(migrated_database_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "UPDATE idempotency_keys SET expires_at = now() - interval '1 minute'"
                    " WHERE key = 'old'"
                )
            )
    finally:
        engine.dispose()

    second = await client.post("/api/v1/incidents", json=ENDPOINTS["incidents"](3), headers=headers)

    assert second.status_code == 201
    assert second.json()["id"] != first.json()["id"]
    assert "Idempotency-Replayed" not in second.headers
