"""The demo catalog seed: services, dependencies, idempotence."""

from collections.abc import AsyncIterator

import httpx
import pytest

from opspilot_api.demo_seed import DEMO_DEPENDENCIES, DEMO_SERVICES, seed
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


async def test_seed_registers_the_demo_shop_and_its_dependencies(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    operator = Caller(factory, new_org(), "operator")
    client.headers.update(operator.headers)

    await seed(client)

    topology = (await client.get("/api/v1/topology")).json()
    names = {n["id"]: n["slug"] for n in topology["nodes"]}
    assert set(names.values()) == {s["slug"] for s in DEMO_SERVICES}
    edges = {(names[e["source_id"]], names[e["target_id"]]) for e in topology["edges"]}
    assert edges == {(s, t) for s, targets in DEMO_DEPENDENCIES.items() for t in targets}
    checkout = next(
        s for s in (await client.get("/api/v1/services")).json()["items"] if s["slug"] == "checkout"
    )
    assert (checkout["namespace"], checkout["deployment_name"]) == ("demo", "checkout")


async def test_seeding_twice_changes_nothing(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    client.headers.update(Caller(factory, new_org(), "operator").headers)

    await seed(client)
    before = (await client.get("/api/v1/topology")).json()
    await seed(client)

    assert (await client.get("/api/v1/topology")).json() == before
