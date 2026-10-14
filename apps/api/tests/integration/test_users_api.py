"""Read-only user directory: roles from the latest sign-in, MANAGE_USERS, organization isolation."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

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


async def sign_in(client: httpx.AsyncClient, caller: Caller) -> str:
    response = await client.get("/api/v1/me", headers=caller.headers)
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def test_administrators_list_their_organizations_users_with_roles(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    org = new_org()
    admin = Caller(factory, org, "administrator")
    viewer = Caller(factory, org, "viewer")
    commander = Caller(factory, org, "incident-commander", "offline_access")
    outsider = Caller(factory, new_org(), "viewer")
    for caller in (viewer, commander, outsider):
        await sign_in(client, caller)

    response = await client.get("/api/v1/users", headers=admin.headers)

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    roles = {tuple(u["roles"]) for u in items}
    assert roles == {("administrator",), ("viewer",), ("incident-commander",)}
    commander_item = next(u for u in items if u["roles"] == ["incident-commander"])
    assert "approve_remediation" in commander_item["permissions"]
    assert "manage_users" not in commander_item["permissions"]
    assert all(u["status"] == "active" for u in items)


async def test_the_list_is_paginated(client: httpx.AsyncClient, factory: TokenFactory) -> None:
    org = new_org()
    admin = Caller(factory, org, "administrator")
    for _ in range(3):
        await sign_in(client, Caller(factory, org, "viewer"))

    seen: list[str] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        body = (await client.get("/api/v1/users", params=params, headers=admin.headers)).json()
        seen += [u["id"] for u in body["items"]]
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert len(seen) == len(set(seen)) == 4


async def test_roles_follow_the_latest_sign_in(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    org = new_org()
    admin = Caller(factory, org, "administrator")
    user = Caller(factory, org, "operator")
    user_id = await sign_in(client, user)
    token = factory.token(sub=user.sub, organization=org, realm_access={"roles": ["viewer"]})
    await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    response = await client.get(f"/api/v1/users/{user_id}", headers=admin.headers)

    assert response.status_code == 200
    assert response.json()["roles"] == ["viewer"]


async def test_a_user_in_another_organization_is_not_found(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    admin = Caller(factory, new_org(), "administrator")
    other_id = await sign_in(client, Caller(factory, new_org(), "viewer"))

    assert (await client.get(f"/api/v1/users/{other_id}", headers=admin.headers)).status_code == 404
    missing = await client.get(f"/api/v1/users/{uuid.uuid4()}", headers=admin.headers)
    assert missing.status_code == 404


@pytest.mark.parametrize("path", ["/api/v1/users", f"/api/v1/users/{uuid.uuid4()}"])
async def test_requires_authentication(client: httpx.AsyncClient, path: str) -> None:
    assert (await client.get(path)).status_code == 401


@pytest.mark.parametrize("roles", [(), ("viewer",), ("operator",), ("incident-commander",)])
async def test_only_administrators_may_view_users(
    client: httpx.AsyncClient, factory: TokenFactory, roles: tuple[str, ...]
) -> None:
    org = new_org()
    caller = Caller(factory, org, *roles)
    user_id = await sign_in(client, Caller(factory, org, "viewer"))

    assert (await client.get("/api/v1/users", headers=caller.headers)).status_code == 403
    single = await client.get(f"/api/v1/users/{user_id}", headers=caller.headers)
    assert single.status_code == 403


async def test_there_is_no_way_to_change_roles(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    org = new_org()
    admin = Caller(factory, org, "administrator")
    user_id = await sign_in(client, Caller(factory, org, "viewer"))

    response = await client.patch(
        f"/api/v1/users/{user_id}", json={"roles": ["administrator"]}, headers=admin.headers
    )

    assert response.status_code == 405
