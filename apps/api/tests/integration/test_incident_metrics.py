"""Command-center incident metrics: MTTA, MTTR, severity breakdowns, scoping."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

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


async def create(client: httpx.AsyncClient, caller: Caller, severity: str) -> str:
    response = await client.post(
        "/api/v1/incidents",
        json={"title": f"{severity} incident", "severity": severity},
        headers=caller.headers,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def set_times(url: str, incident_id: str, **times: datetime | str | None) -> None:
    """Rewrite lifecycle timestamps so durations are known exactly."""
    engine = sa.create_engine(url)
    assignments = ", ".join(f"{name} = :{name}" for name in times)
    with engine.begin() as conn:
        conn.execute(
            sa.text(f"UPDATE incidents SET {assignments} WHERE id = :id"),
            {"id": incident_id, **times},
        )
    engine.dispose()


async def test_mtta_and_mttr_average_over_the_window(
    client: httpx.AsyncClient, factory: TokenFactory, migrated_database_url: str
) -> None:
    operator = Caller(factory, new_org(), "operator")
    now = datetime.now(UTC)
    first = await create(client, operator, "high")
    second = await create(client, operator, "low")
    old = await create(client, operator, "low")
    set_times(
        migrated_database_url,
        first,
        started_at=now - timedelta(hours=2),
        acknowledged_at=now - timedelta(hours=2) + timedelta(minutes=4),
        resolved_at=now - timedelta(hours=1),
        status="RESOLVED",
    )
    set_times(
        migrated_database_url,
        second,
        started_at=now - timedelta(hours=3),
        acknowledged_at=now - timedelta(hours=3) + timedelta(minutes=8),
    )
    set_times(
        migrated_database_url,
        old,
        started_at=now - timedelta(days=40),
        acknowledged_at=now - timedelta(days=40) + timedelta(hours=5),
        resolved_at=now - timedelta(days=39),
        status="RESOLVED",
    )

    response = await client.get(
        "/api/v1/incident-metrics", headers=Caller(factory, operator.org, "viewer").headers
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["window_days"] == 30
    assert body["mtta_seconds"] == pytest.approx(6 * 60)
    assert body["mttr_seconds"] == pytest.approx(60 * 60)
    assert (body["acknowledged"], body["resolved"]) == (2, 1)


async def test_no_data_reports_null_durations(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    viewer = Caller(factory, new_org(), "viewer")

    body = (await client.get("/api/v1/incident-metrics", headers=viewer.headers)).json()

    assert (body["mtta_seconds"], body["mttr_seconds"]) == (None, None)
    assert body["active_by_severity"] == {"critical": 0, "high": 0, "medium": 0, "low": 0}
    assert len(body["daily"]) == 30
    assert all(
        sum(day[s] for s in ("critical", "high", "medium", "low")) == 0 for day in body["daily"]
    )


async def test_severity_breakdowns_count_active_and_daily_incidents(
    client: httpx.AsyncClient, factory: TokenFactory, migrated_database_url: str
) -> None:
    operator = Caller(factory, new_org(), "operator")
    await create(client, operator, "critical")
    await create(client, operator, "critical")
    resolved = await create(client, operator, "high")
    yesterday = await create(client, operator, "medium")
    now = datetime.now(UTC)
    set_times(migrated_database_url, resolved, status="RESOLVED", resolved_at=now)
    set_times(migrated_database_url, yesterday, started_at=now - timedelta(days=1))

    body = (await client.get("/api/v1/incident-metrics?days=7", headers=operator.headers)).json()

    assert body["active_by_severity"] == {"critical": 2, "high": 0, "medium": 1, "low": 0}
    days = {d["date"]: d for d in body["daily"]}
    assert len(days) == 7
    today = days[now.date().isoformat()]
    assert (today["critical"], today["high"]) == (2, 1)
    assert days[(now - timedelta(days=1)).date().isoformat()]["medium"] == 1
    assert list(days) == sorted(days)


async def test_metrics_are_scoped_to_the_organization(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    await create(client, Caller(factory, new_org(), "operator"), "critical")

    body = (
        await client.get(
            "/api/v1/incident-metrics", headers=Caller(factory, new_org(), "viewer").headers
        )
    ).json()

    assert body["active_by_severity"]["critical"] == 0


@pytest.mark.parametrize("days", [0, 91])
async def test_window_is_bounded(
    client: httpx.AsyncClient, factory: TokenFactory, days: int
) -> None:
    viewer = Caller(factory, new_org(), "viewer")

    response = await client.get(f"/api/v1/incident-metrics?days={days}", headers=viewer.headers)

    assert response.status_code == 422


async def test_metrics_require_authentication(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/incident-metrics")).status_code == 401
