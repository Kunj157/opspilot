"""API killed mid-stream: the client reconnects with Last-Event-ID and loses nothing."""

import asyncio
import uuid
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from opspilot_api.db.models import ActorType, Incident, IncidentEvent
from opspilot_api.incidents import service as incidents
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.support.tokens import AUDIENCE, TokenFactory

from chaos.harness import ApiProcess, Controlled, OidcStub


@pytest.fixture
def api(
    postgres: Controlled, redis: Controlled, tokens: TokenFactory, tmp_path: Path
) -> Iterator[tuple[ApiProcess, str]]:
    oidc = OidcStub(tokens.public_key, tokens.kid)
    process = ApiProcess(
        {
            "APP_ENV": "test",
            "DATABASE_URL": postgres.url,
            "REDIS_URL": redis.url,
            "JWT_ISSUER": oidc.issuer,
            "JWT_AUDIENCE": AUDIENCE,
            "EMBEDDING_MODEL": "hashing",
            "SSE_HEARTBEAT_SECONDS": "1",
        },
        str(tmp_path / "api.log"),
    )
    process.start()
    token = tokens.token(
        iss=oidc.issuer,
        sub=uuid.uuid4().hex,
        organization=f"org-{uuid.uuid4().hex[:10]}",
    )
    try:
        yield process, token
    finally:
        process.stop()
        oidc.close()


class Listener:
    """A browser-like SSE client: reconnects after a drop, sending Last-Event-ID."""

    def __init__(self, url: str, token: str) -> None:
        self.url = url
        self.headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}
        self.sequences: list[int] = []
        self.connections = 0
        self.connected = asyncio.Event()

    async def run(self) -> None:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, read=None)) as client:
            while True:
                headers = dict(self.headers)
                if self.sequences:
                    headers["Last-Event-ID"] = str(self.sequences[-1])
                try:
                    async with client.stream("GET", self.url, headers=headers) as response:
                        response.raise_for_status()
                        self.connections += 1
                        self.connected.set()
                        async for line in response.aiter_lines():
                            if line.startswith("id: "):
                                self.sequences.append(int(line[4:]))
                except (httpx.TransportError, httpx.HTTPStatusError):
                    self.connected.clear()
                    await asyncio.sleep(0.2)


async def test_no_timeline_entry_is_lost_across_an_api_restart(
    api: tuple[ApiProcess, str], postgres: Controlled
) -> None:
    process, token = api
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=process.url, headers=headers, timeout=10) as http:
        created = await http.post(
            "/api/v1/incidents", json={"title": "SSE restart", "severity": "high"}
        )
        assert created.status_code == 201
        incident_id = created.json()["id"]
        version = created.json()["version"]

        listener = Listener(f"{process.url}/api/v1/incidents/{incident_id}/stream", token)
        task = asyncio.create_task(listener.run())
        await asyncio.wait_for(listener.connected.wait(), 10)

        async def edit(n: int) -> None:
            nonlocal version
            for i in range(n):
                r = await http.patch(
                    f"/api/v1/incidents/{incident_id}",
                    json={"version": version, "description": f"edit {i}"},
                )
                assert r.status_code == 200
                version = r.json()["version"]

        await edit(5)
        await asyncio.sleep(1)
        process.kill()

        # The worker keeps writing the timeline while the API is down.
        engine = create_async_engine(postgres.url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            incident = await session.get_one(Incident, uuid.UUID(incident_id))
            actor = incidents.Actor(ActorType.SYSTEM, "chaos", incident.organization_id)
            for i in range(5):
                await incidents.note(
                    session,
                    incident,
                    actor,
                    event_type="incident.agent_update",
                    title=f"written while the API was down {i}",
                    metadata={},
                )
            await session.commit()

        restart_seconds = process.start()
        await asyncio.wait_for(listener.connected.wait(), 15)
        await edit(5)

        async with sessions() as session:
            from sqlalchemy import select

            stored = list(
                await session.scalars(
                    select(IncidentEvent.sequence)
                    .where(IncidentEvent.incident_id == uuid.UUID(incident_id))
                    .order_by(IncidentEvent.sequence)
                )
            )
        await engine.dispose()

        for _ in range(50):
            if listener.sequences[-1:] == stored[-1:]:
                break
            await asyncio.sleep(0.2)
        task.cancel()

    # Everything after the first delivered event arrived exactly once, in order.
    first = stored.index(listener.sequences[0])
    assert listener.sequences == stored[first:]
    assert listener.connections == 2
    assert restart_seconds < 60
