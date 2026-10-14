"""PostgreSQL restart: requests fail fast while it is down, the pool recovers after."""

import asyncio
import time

from tests.support.app import Caller, api_client, new_org
from tests.support.tokens import TokenFactory

from chaos.harness import Controlled, wait_for_postgres


async def test_the_pool_recovers_after_a_database_restart(
    postgres: Controlled, redis: Controlled, tokens: TokenFactory
) -> None:
    caller = Caller(tokens, new_org(), "incident-commander")
    async with api_client(
        postgres.url, tokens, redis_url=redis.url, readiness_timeout_seconds=1.0
    ) as client:
        # Fill the pool with connections that the restart will kill.
        warm = await asyncio.gather(
            *(client.get("/api/v1/incidents", headers=caller.headers) for _ in range(10))
        )
        assert {r.status_code for r in warm} == {200}

        postgres.stop()
        try:
            started = time.monotonic()
            ready = await client.get("/api/v1/ready")
            during = await client.get("/api/v1/incidents", headers=caller.headers)
            took = time.monotonic() - started

            assert ready.status_code == 503
            assert ready.json()["checks"]["database"]["status"] == "fail"
            assert during.status_code == 503, "a database outage is unavailability, not a bug"
            assert "Retry-After" in during.headers
            assert took < 5, "requests must fail fast, not hang, while the database is down"
        finally:
            postgres.start()
        wait_for_postgres(postgres)

        # pool_pre_ping replaces the dead connections: no request after recovery fails.
        after = await asyncio.gather(
            *(client.get("/api/v1/incidents", headers=caller.headers) for _ in range(20))
        )
        assert [r.status_code for r in after] == [200] * 20
        assert (await client.get("/api/v1/ready")).status_code == 200
        created = await client.post(
            "/api/v1/incidents",
            json={"title": "Created after the restart", "severity": "low"},
            headers=caller.headers,
        )
        assert created.status_code == 201
