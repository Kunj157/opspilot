"""Server-Sent Events for incidents, against a real server and database."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
import sqlalchemy as sa

from tests.support.app import Caller, new_org
from tests.support.live import live_server
from tests.support.tokens import TokenFactory

pytestmark = pytest.mark.integration


@pytest.fixture
def factory() -> TokenFactory:
    return TokenFactory()


@pytest.fixture
async def base_url(migrated_database_url: str, factory: TokenFactory) -> AsyncIterator[str]:
    async with live_server(migrated_database_url, factory, sse_heartbeat_seconds=0.5) as url:
        yield url


@pytest.fixture
async def http(base_url: str) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=base_url, timeout=10) as c:
        yield c


class Stream:
    """Reads SSE frames from an open response into a queue."""

    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.frames: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._task = asyncio.create_task(self._read())

    async def _read(self) -> None:
        frame: dict[str, Any] = {}
        async for line in self.response.aiter_lines():
            if line == "":
                if frame:
                    await self.frames.put(frame)
                frame = {}
            elif line.startswith(":"):
                await self.frames.put({"comment": line[1:].strip()})
            else:
                field, _, value = line.partition(":")
                frame[field] = value.lstrip()

    async def next_event(self, within: float = 5) -> dict[str, Any]:
        # One deadline for the whole wait: heartbeats must not extend it.
        async with asyncio.timeout(within):
            while True:
                frame = await self.frames.get()
                if "data" in frame:
                    data = json.loads(frame["data"])
                    # The SSE id is the event's sequence number (used for Last-Event-ID).
                    assert int(frame["id"]) == data["sequence"]
                    return {**data, "event": frame["event"]}

    async def next_comment(self, within: float = 5) -> str:
        async with asyncio.timeout(within):
            while True:
                frame = await self.frames.get()
                if "comment" in frame:
                    return str(frame["comment"])

    async def assert_silent(self, seconds: float = 1.0) -> None:
        try:
            event = await self.next_event(within=seconds)
        except TimeoutError:
            return
        raise AssertionError(f"unexpected event {event}")

    def close(self) -> None:
        self._task.cancel()


@asynccontextmanager
async def stream(
    http: httpx.AsyncClient, path: str, caller: Caller, **headers: str
) -> AsyncIterator[Stream]:
    async with http.stream("GET", path, headers={**caller.headers, **headers}) as response:
        assert response.status_code == 200, await response.aread()
        assert response.headers["content-type"].startswith("text/event-stream")
        s = Stream(response)
        try:
            await s.next_comment()  # the stream announces itself once subscribed
            yield s
        finally:
            s.close()


async def create(
    http: httpx.AsyncClient, caller: Caller, title: str = "Checkout down"
) -> dict[str, Any]:
    response = await http.post(
        "/api/v1/incidents", json={"title": title, "severity": "high"}, headers=caller.headers
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def test_organization_stream_receives_new_incidents(
    http: httpx.AsyncClient, factory: TokenFactory
) -> None:
    operator = Caller(factory, new_org(), "operator")
    async with stream(http, "/api/v1/incidents/stream", operator) as live:
        incident = await create(http, operator)

        event = await live.next_event()

    assert event["event"] == "incident.created"
    assert event["incident"]["id"] == incident["id"]
    assert event["incident"]["status"] == "DETECTED"


async def test_incident_stream_follows_one_incident(
    http: httpx.AsyncClient, factory: TokenFactory
) -> None:
    operator = Caller(factory, new_org(), "operator")
    watched, other = await create(http, operator, "Watched"), await create(http, operator, "Other")
    async with stream(http, f"/api/v1/incidents/{watched['id']}/stream", operator) as live:
        await http.post(
            f"/api/v1/incidents/{other['id']}/investigate",
            json={"version": 1},
            headers=operator.headers,
        )
        await http.post(
            f"/api/v1/incidents/{watched['id']}/investigate",
            json={"version": 1},
            headers=operator.headers,
        )

        event = await live.next_event()

    assert event["event"] == "incident.status_changed"
    assert event["incident"]["id"] == watched["id"]
    assert event["metadata"] == {"from": "DETECTED", "to": "INVESTIGATING"}


async def test_other_organizations_hear_nothing(
    http: httpx.AsyncClient, factory: TokenFactory
) -> None:
    async with stream(
        http, "/api/v1/incidents/stream", Caller(factory, new_org(), "viewer")
    ) as live:
        await create(http, Caller(factory, new_org(), "operator"))

        await live.assert_silent()


async def test_last_event_id_replays_missed_events(
    http: httpx.AsyncClient, factory: TokenFactory
) -> None:
    operator = Caller(factory, new_org(), "operator")
    incident = await create(http, operator)
    timeline = (
        await http.get(f"/api/v1/incidents/{incident['id']}/events", headers=operator.headers)
    ).json()
    first_sequence = timeline["items"][0]["sequence"]
    await http.post(
        f"/api/v1/incidents/{incident['id']}/investigate",
        json={"version": 1},
        headers=operator.headers,
    )
    await http.post(
        f"/api/v1/incidents/{incident['id']}/acknowledge",
        json={"version": 2},
        headers=operator.headers,
    )

    async with stream(
        http,
        f"/api/v1/incidents/{incident['id']}/stream",
        operator,
        **{"Last-Event-ID": str(first_sequence)},
    ) as live:
        replayed = [await live.next_event(), await live.next_event()]

    assert [e["event"] for e in replayed] == ["incident.status_changed", "incident.acknowledged"]
    assert replayed[0]["sequence"] > first_sequence


async def test_heartbeats_keep_idle_streams_open(
    http: httpx.AsyncClient, factory: TokenFactory
) -> None:
    async with stream(
        http, "/api/v1/incidents/stream", Caller(factory, new_org(), "viewer")
    ) as live:
        assert await live.next_comment(within=3) == "heartbeat"


async def test_streams_require_authentication_and_ownership(
    http: httpx.AsyncClient, factory: TokenFactory
) -> None:
    incident = await create(http, Caller(factory, new_org(), "operator"))

    anonymous = await http.get("/api/v1/incidents/stream")
    foreign = await http.get(
        f"/api/v1/incidents/{incident['id']}/stream",
        headers=Caller(factory, new_org(), "administrator").headers,
    )

    assert (anonymous.status_code, foreign.status_code) == (401, 404)


async def test_events_still_arrive_after_the_listener_connection_drops(
    http: httpx.AsyncClient, factory: TokenFactory, migrated_database_url: str
) -> None:
    operator = Caller(factory, new_org(), "operator")
    async with stream(http, "/api/v1/incidents/stream", operator) as live:
        engine = sa.create_engine(migrated_database_url)
        try:
            with engine.begin() as conn:
                killed = conn.execute(
                    sa.text(
                        "SELECT count(pg_terminate_backend(pid)) FROM pg_stat_activity"
                        " WHERE query ILIKE 'LISTEN%' AND pid <> pg_backend_pid()"
                    )
                ).scalar_one()
        finally:
            engine.dispose()
        assert killed >= 1
        incident = await create(http, operator)

        event = await live.next_event(within=10)

    assert event["incident"]["id"] == incident["id"]
