"""Incident HTTP API: lifecycle, filters, conflicts, permissions, and tenancy."""

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


@pytest.fixture
def operator(factory: TokenFactory) -> Caller:
    return Caller(factory, new_org(), "operator")


async def create(client: httpx.AsyncClient, caller: Caller, **overrides: Any) -> dict[str, Any]:
    body = {"title": "Checkout errors rising", "severity": "high", **overrides}
    response = await client.post("/api/v1/incidents", json=body, headers=caller.headers)
    assert response.status_code == 201, response.text
    return dict(response.json())


async def act(
    client: httpx.AsyncClient, caller: Caller, incident: dict[str, Any], action: str
) -> httpx.Response:
    return await client.post(
        f"/api/v1/incidents/{incident['id']}/{action}",
        json={"version": incident["version"]},
        headers=caller.headers,
    )


async def test_create_returns_a_detected_incident(
    client: httpx.AsyncClient, operator: Caller
) -> None:
    incident = await create(client, operator, description="5xx on /pay")

    assert incident["status"] == "DETECTED"
    assert incident["version"] == 1
    assert incident["source"] == "manual"
    assert incident["allowed_transitions"] == ["INVESTIGATING"]


@pytest.mark.parametrize(
    "body",
    [
        {"title": "x", "severity": "apocalyptic"},
        {"title": "", "severity": "low"},
        {"severity": "low"},
    ],
    ids=["bad-severity", "empty-title", "missing-title"],
)
async def test_invalid_create_is_422(
    client: httpx.AsyncClient, operator: Caller, body: dict[str, Any]
) -> None:
    response = await client.post("/api/v1/incidents", json=body, headers=operator.headers)

    assert response.status_code == 422


async def test_service_must_belong_to_the_organization(
    client: httpx.AsyncClient, factory: TokenFactory, operator: Caller
) -> None:
    foreign = Caller(factory, new_org(), "operator")
    service = await client.post(
        "/api/v1/services", json={"name": "Pay", "slug": "pay"}, headers=foreign.headers
    )

    response = await client.post(
        "/api/v1/incidents",
        json={"title": "x", "severity": "low", "service_id": service.json()["id"]},
        headers=operator.headers,
    )

    assert response.status_code == 422


async def test_manual_lifecycle_to_resolved(client: httpx.AsyncClient, operator: Caller) -> None:
    incident = await create(client, operator)

    incident = (await act(client, operator, incident, "acknowledge")).json()
    incident = (await act(client, operator, incident, "investigate")).json()
    moved = await client.patch(
        f"/api/v1/incidents/{incident['id']}",
        json={"version": incident["version"], "status": "MONITORING"},
        headers=operator.headers,
    )
    resolved = await act(client, operator, moved.json(), "resolve")

    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert body["status"] == "RESOLVED"
    assert body["acknowledged_at"]
    assert body["resolved_at"]
    assert body["allowed_transitions"] == []
    timeline = await client.get(
        f"/api/v1/incidents/{incident['id']}/events", headers=operator.headers
    )
    assert [e["event_type"] for e in timeline.json()["items"]] == [
        "incident.created",
        "incident.acknowledged",
        "incident.status_changed",
        "incident.status_changed",
        "incident.status_changed",
    ]


async def test_acknowledge_assigns_the_caller(client: httpx.AsyncClient, operator: Caller) -> None:
    me = (await client.get("/api/v1/me", headers=operator.headers)).json()
    incident = await create(client, operator)

    acknowledged = (await act(client, operator, incident, "acknowledge")).json()

    assert acknowledged["assigned_user_id"] == me["id"]


async def test_disallowed_transition_is_409_with_reason(
    client: httpx.AsyncClient, operator: Caller
) -> None:
    incident = await create(client, operator)

    response = await act(client, operator, incident, "resolve")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "invalid_transition"


async def test_stale_version_is_409_with_current_version(
    client: httpx.AsyncClient, operator: Caller
) -> None:
    incident = await create(client, operator)
    await act(client, operator, incident, "investigate")

    response = await act(client, operator, incident, "acknowledge")  # still sends version 1

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "stale_version",
        "message": "The incident was changed by someone else. Reload and try again.",
        "current_version": 2,
    }


async def test_patch_details_and_status_must_be_separate(
    client: httpx.AsyncClient, operator: Caller
) -> None:
    incident = await create(client, operator)

    response = await client.patch(
        f"/api/v1/incidents/{incident['id']}",
        json={"version": 1, "severity": "critical", "status": "INVESTIGATING"},
        headers=operator.headers,
    )

    assert response.status_code == 422


async def test_patch_updates_details(client: httpx.AsyncClient, operator: Caller) -> None:
    incident = await create(client, operator)

    response = await client.patch(
        f"/api/v1/incidents/{incident['id']}",
        json={"version": 1, "severity": "critical", "title": "Checkout down"},
        headers=operator.headers,
    )

    assert response.status_code == 200
    assert (response.json()["severity"], response.json()["title"], response.json()["version"]) == (
        "critical",
        "Checkout down",
        2,
    )


async def test_cannot_assign_a_user_from_another_organization(
    client: httpx.AsyncClient, factory: TokenFactory, operator: Caller
) -> None:
    stranger = Caller(factory, new_org(), "viewer")
    stranger_id = (await client.get("/api/v1/me", headers=stranger.headers)).json()["id"]
    incident = await create(client, operator)

    response = await client.patch(
        f"/api/v1/incidents/{incident['id']}",
        json={"version": 1, "assigned_user_id": stranger_id},
        headers=operator.headers,
    )

    assert response.status_code == 422


@pytest.mark.parametrize("action", ["acknowledge", "investigate", "resolve"])
async def test_viewer_cannot_change_incidents(
    client: httpx.AsyncClient, factory: TokenFactory, action: str
) -> None:
    org = new_org()
    incident = await create(client, Caller(factory, org, "operator"))
    viewer = Caller(factory, org, "viewer")

    create_attempt = await client.post(
        "/api/v1/incidents", json={"title": "x", "severity": "low"}, headers=viewer.headers
    )
    action_attempt = await act(client, viewer, incident, action)

    assert (create_attempt.status_code, action_attempt.status_code) == (403, 403)


async def test_other_organizations_get_404(
    client: httpx.AsyncClient, factory: TokenFactory, operator: Caller
) -> None:
    incident = await create(client, operator)
    outsider = Caller(factory, new_org(), "administrator")

    responses = [
        await client.get(f"/api/v1/incidents/{incident['id']}", headers=outsider.headers),
        await client.get(f"/api/v1/incidents/{incident['id']}/events", headers=outsider.headers),
        await act(client, outsider, incident, "investigate"),
    ]

    assert [r.status_code for r in responses] == [404, 404, 404]
    listed = await client.get("/api/v1/incidents", headers=outsider.headers)
    assert incident["id"] not in {i["id"] for i in listed.json()["items"]}


async def test_list_filters(client: httpx.AsyncClient, factory: TokenFactory) -> None:
    org = new_org()
    operator = Caller(factory, org, "operator")
    service = (
        await client.post(
            "/api/v1/services", json={"name": "Pay", "slug": "pay"}, headers=operator.headers
        )
    ).json()
    critical = await create(client, operator, severity="critical", service_id=service["id"])
    low = await create(client, operator, severity="low", source="detector")
    investigating = (await act(client, operator, low, "investigate")).json()

    async def ids(**params: Any) -> set[str]:
        response = await client.get("/api/v1/incidents", params=params, headers=operator.headers)
        assert response.status_code == 200, response.text
        return {i["id"] for i in response.json()["items"]}

    assert await ids() == {critical["id"], low["id"]}
    assert await ids(severity="critical") == {critical["id"]}
    assert await ids(status="INVESTIGATING") == {investigating["id"]}
    assert await ids(status=["DETECTED", "INVESTIGATING"]) == {critical["id"], low["id"]}
    assert await ids(service_id=service["id"]) == {critical["id"]}
    assert await ids(source="detector") == {low["id"]}
    assert await ids(since="2000-01-01T00:00:00Z") == {critical["id"], low["id"]}
    assert await ids(until="2000-01-01T00:00:00Z") == set()


async def test_list_filters_by_assignee(client: httpx.AsyncClient, operator: Caller) -> None:
    me = (await client.get("/api/v1/me", headers=operator.headers)).json()
    mine = (await act(client, operator, await create(client, operator), "acknowledge")).json()
    await create(client, operator)

    response = await client.get(
        "/api/v1/incidents", params={"assigned_user_id": me["id"]}, headers=operator.headers
    )

    assert [i["id"] for i in response.json()["items"]] == [mine["id"]]


async def test_list_paginates_newest_first(client: httpx.AsyncClient, operator: Caller) -> None:
    created = [await create(client, operator, title=f"Incident {n}") for n in range(5)]

    first = (
        await client.get("/api/v1/incidents", params={"limit": 3}, headers=operator.headers)
    ).json()
    second = (
        await client.get(
            "/api/v1/incidents",
            params={"limit": 3, "cursor": first["next_cursor"]},
            headers=operator.headers,
        )
    ).json()

    listed = [i["id"] for i in first["items"] + second["items"]]
    assert listed == [i["id"] for i in reversed(created)]
    assert second["next_cursor"] is None


async def test_unknown_incident_is_404(client: httpx.AsyncClient, operator: Caller) -> None:
    response = await client.get(f"/api/v1/incidents/{uuid.uuid4()}", headers=operator.headers)

    assert response.status_code == 404
