"""Readiness against real PostgreSQL and Redis containers.

These tests must fail, not skip, when Docker is unavailable
(DEVELOPMENT_WORKFLOW.md §5).
"""

from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from asgi_lifespan import LifespanManager
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from opspilot_api.config import Settings
from opspilot_api.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def postgres() -> Iterator[PostgresContainer]:
    with PostgresContainer("pgvector/pgvector:0.8.0-pg17", driver="psycopg") as container:
        yield container


@pytest.fixture(scope="module")
def redis_container() -> Iterator[RedisContainer]:
    with RedisContainer("redis:7.4-alpine") as container:
        yield container


def _redis_url(container: RedisContainer) -> str:
    host = container.get_container_host_ip()
    port = container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"


async def _client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings)
    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_ready_with_real_dependencies(
    postgres: PostgresContainer, redis_container: RedisContainer
) -> None:
    settings = Settings(
        app_env="test",
        database_url=postgres.get_connection_url(),
        redis_url=_redis_url(redis_container),
    )
    async for client in _client(settings):
        response = await client.get("/api/v1/ready")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ready"


async def test_not_ready_when_database_unreachable(redis_container: RedisContainer) -> None:
    settings = Settings(
        app_env="test",
        database_url="postgresql+psycopg://opspilot:opspilot@127.0.0.1:1/opspilot",
        redis_url=_redis_url(redis_container),
        readiness_timeout_seconds=2.0,
    )
    async for client in _client(settings):
        response = await client.get("/api/v1/ready")

    assert response.status_code == 503
    checks = response.json()["checks"]
    assert checks["database"]["status"] == "fail"
    assert checks["redis"]["status"] == "ok"


async def test_not_ready_when_redis_unreachable(postgres: PostgresContainer) -> None:
    settings = Settings(
        app_env="test",
        database_url=postgres.get_connection_url(),
        redis_url="redis://127.0.0.1:1/0",
        readiness_timeout_seconds=2.0,
    )
    async for client in _client(settings):
        response = await client.get("/api/v1/ready")

    assert response.status_code == 503
    checks = response.json()["checks"]
    assert checks["redis"]["status"] == "fail"
    assert checks["database"]["status"] == "ok"
