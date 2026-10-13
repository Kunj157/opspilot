"""Service dependencies and the topology view: validation, permissions, tenancy, audit."""

from collections.abc import AsyncIterator

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


async def make_service(client: httpx.AsyncClient, caller: Caller, slug: str) -> str:
    response = await client.post(
        "/api/v1/services", json={"name": slug.title(), "slug": slug}, headers=caller.headers
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def set_dependencies(
    client: httpx.AsyncClient, caller: Caller, service_id: str, targets: list[str]
) -> httpx.Response:
    return await client.put(
        f"/api/v1/services/{service_id}/dependencies",
        json={"target_ids": targets},
        headers=caller.headers,
    )


async def test_operator_replaces_and_reads_dependencies(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    operator = Caller(factory, new_org(), "operator")
    checkout = await make_service(client, operator, "checkout")
    payment = await make_service(client, operator, "payment")
    inventory = await make_service(client, operator, "inventory")

    first = await set_dependencies(client, operator, checkout, [payment, inventory])
    second = await set_dependencies(client, operator, checkout, [inventory, inventory])
    read = await client.get(
        f"/api/v1/services/{checkout}/dependencies",
        headers=Caller(factory, operator.org, "viewer").headers,
    )

    assert first.status_code == 200, first.text
    assert sorted(s["slug"] for s in first.json()["items"]) == ["inventory", "payment"]
    assert [s["slug"] for s in second.json()["items"]] == ["inventory"]
    assert read.json() == second.json()


async def test_a_service_cannot_depend_on_itself(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    operator = Caller(factory, new_org(), "operator")
    checkout = await make_service(client, operator, "checkout")

    response = await set_dependencies(client, operator, checkout, [checkout])

    assert response.status_code == 422


async def test_targets_in_another_organization_are_rejected(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    operator = Caller(factory, new_org(), "operator")
    checkout = await make_service(client, operator, "checkout")
    foreign = await make_service(client, Caller(factory, new_org(), "operator"), "payment")

    response = await set_dependencies(client, operator, checkout, [foreign])

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "target_ids"]


async def test_viewer_cannot_change_dependencies(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    operator = Caller(factory, new_org(), "operator")
    checkout = await make_service(client, operator, "checkout")
    payment = await make_service(client, operator, "payment")

    response = await set_dependencies(
        client, Caller(factory, operator.org, "viewer"), checkout, [payment]
    )

    assert response.status_code == 403


async def test_other_organizations_cannot_read_or_change_dependencies(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    owner = Caller(factory, new_org(), "operator")
    checkout = await make_service(client, owner, "checkout")
    outsider = Caller(factory, new_org(), "administrator")

    read = await client.get(f"/api/v1/services/{checkout}/dependencies", headers=outsider.headers)
    write = await set_dependencies(client, outsider, checkout, [])

    assert (read.status_code, write.status_code) == (404, 404)


async def test_changing_dependencies_is_audited(
    client: httpx.AsyncClient, factory: TokenFactory, migrated_database_url: str
) -> None:
    operator = Caller(factory, new_org(), "operator")
    checkout = await make_service(client, operator, "checkout")
    payment = await make_service(client, operator, "payment")

    await set_dependencies(client, operator, checkout, [payment])

    engine = sa.create_engine(migrated_database_url)
    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT metadata_json FROM audit_logs"
                " WHERE action = 'service.dependencies_updated' AND resource_id = :id"
            ),
            {"id": checkout},
        ).one()
    engine.dispose()
    assert row.metadata_json == {"target_ids": [payment]}


async def test_topology_lists_services_edges_and_active_incidents(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    org = new_org()
    operator = Caller(factory, org, "operator")
    checkout = await make_service(client, operator, "checkout")
    payment = await make_service(client, operator, "payment")
    await set_dependencies(client, operator, checkout, [payment])
    incident = (
        await client.post(
            "/api/v1/incidents",
            json={"title": "Payment errors", "severity": "high", "service_id": payment},
            headers=operator.headers,
        )
    ).json()
    await client.post(
        f"/api/v1/incidents/{incident['id']}/investigate",
        json={"version": incident["version"]},
        headers=operator.headers,
    )
    resolved = (
        await client.post(
            "/api/v1/incidents",
            json={"title": "Old checkout issue", "severity": "low", "service_id": checkout},
            headers=operator.headers,
        )
    ).json()
    url = f"/api/v1/incidents/{resolved['id']}"
    step = await client.post(f"{url}/investigate", json={"version": 1}, headers=operator.headers)
    step = await client.patch(
        url,
        json={"version": step.json()["version"], "status": "MONITORING"},
        headers=operator.headers,
    )
    step = await client.post(
        f"{url}/resolve", json={"version": step.json()["version"]}, headers=operator.headers
    )
    assert step.json()["status"] == "RESOLVED", step.text
    await make_service(client, Caller(factory, new_org(), "operator"), "elsewhere")

    response = await client.get("/api/v1/topology", headers=Caller(factory, org, "viewer").headers)

    assert response.status_code == 200, response.text
    body = response.json()
    nodes = {n["slug"]: n for n in body["nodes"]}
    assert set(nodes) == {"checkout", "payment"}
    assert (nodes["payment"]["active_incidents"], nodes["payment"]["investigating"]) == (1, True)
    assert (nodes["checkout"]["active_incidents"], nodes["checkout"]["investigating"]) == (0, False)
    assert body["edges"] == [{"source_id": checkout, "target_id": payment}]


async def test_topology_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/topology")

    assert response.status_code == 401
