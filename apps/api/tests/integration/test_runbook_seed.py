"""Loading docs/runbooks into the library: idempotent upsert by slug."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from opspilot_api.runbook_seed import seed_runbooks
from opspilot_api.runbooks.document import parse
from tests.support.app import Caller, api_client, new_org
from tests.support.tokens import TokenFactory

pytestmark = pytest.mark.integration

DOCS = Path(__file__).resolve().parents[4] / "docs" / "runbooks"


@pytest.fixture
async def client(migrated_database_url: str) -> AsyncIterator[httpx.AsyncClient]:
    factory = TokenFactory()
    async with api_client(migrated_database_url, factory) as c:
        c.headers.update(Caller(factory, new_org(), "operator").headers)
        yield c


async def test_seeding_twice_loads_each_runbook_once(client: httpx.AsyncClient) -> None:
    first = await seed_runbooks(client, DOCS)
    second = await seed_runbooks(client, DOCS)

    items = (await client.get("/api/v1/runbooks")).json()["items"]
    assert first == {"created": 6, "updated": 0, "unchanged": 0}
    assert second == {"created": 0, "updated": 0, "unchanged": 6}
    assert {r["slug"] for r in items} >= {"checkout-high-error-rate", "deployment-rollback"}
    versions = {
        path.stem: parse(path.read_text()).version
        for path in DOCS.glob("*.md")
        if path.name != "README.md"
    }
    assert {r["slug"]: r["version"] for r in items} == versions
