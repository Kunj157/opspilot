"""Redis down: the API keeps serving, readiness reports it, and recovers."""

import asyncio
import time

from tests.support.app import Caller, api_client, new_org
from tests.support.tokens import TokenFactory

from chaos.harness import Controlled


async def test_api_degrades_gracefully_while_redis_is_down(
    postgres: Controlled, redis: Controlled, tokens: TokenFactory
) -> None:
    caller = Caller(tokens, new_org(), "incident-commander")
    async with api_client(
        postgres.url, tokens, redis_url=redis.url, readiness_timeout_seconds=1.0
    ) as client:
        ready = await client.get("/api/v1/ready")
        assert ready.status_code == 200

        redis.stop()
        try:
            started = time.monotonic()
            ready = await client.get("/api/v1/ready")
            took = time.monotonic() - started

            assert ready.status_code == 503
            assert ready.json()["checks"]["redis"] == {"status": "fail", "detail": "unavailable"}
            assert ready.json()["checks"]["database"]["status"] == "ok"
            assert took < 3, "readiness must answer within its per-check timeout"
            # Nothing on the request path needs Redis: reads and writes keep working.
            listed = await client.get("/api/v1/incidents", headers=caller.headers)
            created = await client.post(
                "/api/v1/incidents",
                json={"title": "Created while Redis is down", "severity": "low"},
                headers=caller.headers,
            )
            assert listed.status_code == 200
            assert created.status_code == 201
        finally:
            redis.start()

        recovery = time.monotonic()
        while (await client.get("/api/v1/ready")).status_code != 200:
            assert time.monotonic() - recovery < 30, "readiness did not recover"
            await asyncio.sleep(0.5)
