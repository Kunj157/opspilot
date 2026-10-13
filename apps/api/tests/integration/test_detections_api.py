"""GET /incidents/{id}/detections: content, ordering, permissions, tenancy."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from opspilot_api.db.models import Service
from opspilot_api.detection.rules import Decision, ErrorRateRule, Outcome
from opspilot_api.detection.service import apply_decision
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


async def detected_incident(client: httpx.AsyncClient, url: str, caller: Caller) -> str:
    """A service created through the API, then two detector decisions about it."""
    created = await client.post(
        "/api/v1/services", json={"name": "Checkout", "slug": "checkout"}, headers=caller.headers
    )
    service_id = created.json()["id"]
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    rule = ErrorRateRule()
    now = datetime.now(UTC)
    incident = None
    # One evaluation cycle per decision, as the worker runs them.
    for minutes_ago, outcome, rate in [(2, Outcome.TRIGGERED, 0.3), (1, Outcome.ONGOING, 0.5)]:
        async with sessions() as session:
            service = await session.scalar(select(Service).where(Service.id == service_id))
            assert service is not None
            end = now - timedelta(minutes=minutes_ago)
            decision = Decision(
                outcome, rate / rule.threshold, rule.threshold, {"error_rate": rate}
            )
            incident = await apply_decision(
                session,
                service,
                rule,
                decision,
                window_start=end - timedelta(minutes=1),
                window_end=end,
            )
            await session.commit()
    await engine.dispose()
    assert incident is not None
    return str(incident.id)


async def test_viewer_reads_detections_newest_first(
    client: httpx.AsyncClient, factory: TokenFactory, migrated_database_url: str
) -> None:
    operator = Caller(factory, new_org(), "operator")
    incident_id = await detected_incident(client, migrated_database_url, operator)

    response = await client.get(
        f"/api/v1/incidents/{incident_id}/detections",
        headers=Caller(factory, operator.org, "viewer").headers,
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [i["outcome"] for i in items] == ["ongoing", "triggered"]
    assert items[1]["score"] == pytest.approx(6.0)
    assert items[1]["features"] == {"error_rate": 0.3}
    assert items[1]["detector"] == "error-rate"


async def test_detector_incidents_are_listed_with_their_source(
    client: httpx.AsyncClient, factory: TokenFactory, migrated_database_url: str
) -> None:
    operator = Caller(factory, new_org(), "operator")
    incident_id = await detected_incident(client, migrated_database_url, operator)

    incident = (
        await client.get(f"/api/v1/incidents/{incident_id}", headers=operator.headers)
    ).json()

    assert (incident["source"], incident["title"]) == ("detector", "High error rate on Checkout")


async def test_other_organizations_get_404(
    client: httpx.AsyncClient, factory: TokenFactory, migrated_database_url: str
) -> None:
    incident_id = await detected_incident(
        client, migrated_database_url, Caller(factory, new_org(), "operator")
    )

    response = await client.get(
        f"/api/v1/incidents/{incident_id}/detections",
        headers=Caller(factory, new_org(), "administrator").headers,
    )

    assert response.status_code == 404


async def test_detections_require_authentication(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/incidents/00000000-0000-4000-8000-000000000000/detections")

    assert response.status_code == 401
