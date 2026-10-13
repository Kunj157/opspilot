"""Service catalog API: CRUD, validation, permissions, tenancy, and audit."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import sqlalchemy as sa

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


def checkout(**overrides: Any) -> dict[str, Any]:
    body = {
        "name": "Checkout",
        "slug": "checkout",
        "description": "Takes payment and places orders",
        "owner_team": "payments",
        "repository_url": "https://github.com/example/checkout",
        "namespace": "demo",
        "deployment_name": "checkout",
    }
    body.update(overrides)
    return body


async def test_operator_creates_and_reads_a_service(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    operator = Caller(factory, new_org(), "operator")

    created = await client.post("/api/v1/services", json=checkout(), headers=operator.headers)

    assert created.status_code == 201, created.text
    service = created.json()
    assert service["slug"] == "checkout"
    assert service["health_status"] == "unknown"
    fetched = await client.get(f"/api/v1/services/{service['id']}", headers=operator.headers)
    assert fetched.json() == service


async def test_list_is_sorted_by_name_and_scoped_to_the_organization(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    org = new_org()
    operator = Caller(factory, org, "operator")
    for name in ["Payment", "Checkout", "Inventory"]:
        await client.post(
            "/api/v1/services",
            json=checkout(name=name, slug=name.lower()),
            headers=operator.headers,
        )
    await client.post(
        "/api/v1/services",
        json=checkout(name="Other"),
        headers=Caller(factory, new_org(), "operator").headers,
    )

    response = await client.get("/api/v1/services", headers=Caller(factory, org, "viewer").headers)

    assert [s["name"] for s in response.json()["items"]] == ["Checkout", "Inventory", "Payment"]


async def test_viewer_cannot_create(client: httpx.AsyncClient, factory: TokenFactory) -> None:
    response = await client.post(
        "/api/v1/services", json=checkout(), headers=Caller(factory, new_org(), "viewer").headers
    )

    assert response.status_code == 403


async def test_other_organizations_cannot_see_or_change_a_service(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    owner = Caller(factory, new_org(), "operator")
    service_id = (
        await client.post("/api/v1/services", json=checkout(), headers=owner.headers)
    ).json()["id"]
    outsider = Caller(factory, new_org(), "administrator")

    read = await client.get(f"/api/v1/services/{service_id}", headers=outsider.headers)
    write = await client.patch(
        f"/api/v1/services/{service_id}", json={"name": "Hijacked"}, headers=outsider.headers
    )

    assert (read.status_code, write.status_code) == (404, 404)


async def test_duplicate_slug_in_the_same_organization_conflicts(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    org = new_org()
    operator = Caller(factory, org, "operator")
    await client.post("/api/v1/services", json=checkout(), headers=operator.headers)

    again = await client.post(
        "/api/v1/services", json=checkout(name="Again"), headers=operator.headers
    )
    elsewhere = await client.post(
        "/api/v1/services", json=checkout(), headers=Caller(factory, new_org(), "operator").headers
    )

    assert again.status_code == 409
    assert elsewhere.status_code == 201


@pytest.mark.parametrize(
    "overrides",
    [
        {"slug": "Not A Slug"},
        {"slug": "-leading"},
        {"slug": "x"},
        {"name": ""},
        {"namespace": "Bad_Namespace"},
        {"repository_url": "ftp://example.com/repo"},
        {"health_status": "healthy"},
    ],
    ids=[
        "slug-spaces",
        "slug-leading-dash",
        "slug-short",
        "empty-name",
        "namespace",
        "url-scheme",
        "health-not-settable",
    ],
)
async def test_invalid_input_is_422(
    client: httpx.AsyncClient, factory: TokenFactory, overrides: dict[str, Any]
) -> None:
    response = await client.post(
        "/api/v1/services",
        json=checkout(**overrides),
        headers=Caller(factory, new_org(), "operator").headers,
    )

    assert response.status_code == 422


async def test_patch_updates_only_the_given_fields(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    operator = Caller(factory, new_org(), "operator")
    service = (
        await client.post("/api/v1/services", json=checkout(), headers=operator.headers)
    ).json()

    response = await client.patch(
        f"/api/v1/services/{service['id']}",
        json={"owner_team": "checkout-team"},
        headers=operator.headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        **service,
        "owner_team": "checkout-team",
        "updated_at": response.json()["updated_at"],
    }


async def test_unknown_service_is_404(client: httpx.AsyncClient, factory: TokenFactory) -> None:
    response = await client.get(
        f"/api/v1/services/{uuid.uuid4()}", headers=Caller(factory, new_org(), "viewer").headers
    )

    assert response.status_code == 404


async def test_changes_are_audited(
    client: httpx.AsyncClient, factory: TokenFactory, migrated_database_url: str
) -> None:
    operator = Caller(factory, new_org(), "operator")
    service = (
        await client.post("/api/v1/services", json=checkout(), headers=operator.headers)
    ).json()
    await client.patch(
        f"/api/v1/services/{service['id']}", json={"name": "Checkout v2"}, headers=operator.headers
    )

    engine = sa.create_engine(migrated_database_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                sa.text(
                    "SELECT action, metadata_json FROM audit_logs"
                    " WHERE resource_type = 'service' AND resource_id = :id ORDER BY created_at"
                ),
                {"id": service["id"]},
            ).all()
    finally:
        engine.dispose()
    assert [r.action for r in rows] == ["service.created", "service.updated"]
    assert rows[1].metadata_json == {"changed": ["name"]}
