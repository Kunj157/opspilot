import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI

from opspilot_api.config import Settings
from opspilot_api.main import create_app
from opspilot_api.readiness import ReadinessCheck, get_readiness_checks


async def _ok() -> None:
    return None


async def _broken() -> None:
    raise ConnectionError("password authentication failed for user secret-user")


async def _hangs() -> None:
    await asyncio.sleep(10)


async def _client_with_checks(
    app: FastAPI, checks: dict[str, ReadinessCheck]
) -> AsyncIterator[httpx.AsyncClient]:
    app.dependency_overrides[get_readiness_checks] = lambda: checks
    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_ready_when_all_checks_pass(app: FastAPI) -> None:
    async for client in _client_with_checks(app, {"database": _ok, "redis": _ok}):
        response = await client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {
            "config": {"status": "ok", "detail": None},
            "database": {"status": "ok", "detail": None},
            "redis": {"status": "ok", "detail": None},
        },
    }


async def test_not_ready_when_a_dependency_fails(app: FastAPI) -> None:
    async for client in _client_with_checks(app, {"database": _broken, "redis": _ok}):
        response = await client.get("/api/v1/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"] == {"status": "fail", "detail": "unavailable"}
    assert body["checks"]["redis"]["status"] == "ok"


async def test_failure_details_do_not_leak_internals(app: FastAPI) -> None:
    async for client in _client_with_checks(app, {"database": _broken, "redis": _ok}):
        response = await client.get("/api/v1/ready")

    assert "secret-user" not in response.text
    assert "password" not in response.text


async def test_slow_dependency_times_out(settings: Settings) -> None:
    app = create_app(settings.model_copy(update={"readiness_timeout_seconds": 0.05}))
    async for client in _client_with_checks(app, {"database": _hangs, "redis": _ok}):
        response = await client.get("/api/v1/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["database"] == {"status": "fail", "detail": "timeout"}


@pytest.mark.parametrize(
    ("missing", "expected_detail"),
    [
        ({"database_url": None}, "missing: DATABASE_URL"),
        ({"redis_url": None}, "missing: REDIS_URL"),
        ({"database_url": None, "redis_url": None}, "missing: DATABASE_URL, REDIS_URL"),
    ],
)
async def test_not_ready_when_required_config_missing(
    settings: Settings, missing: dict[str, None], expected_detail: str
) -> None:
    app = create_app(settings.model_copy(update=missing))
    async for client in _client_with_checks(app, {}):
        response = await client.get("/api/v1/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["config"] == {"status": "fail", "detail": expected_detail}
