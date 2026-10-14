from collections.abc import AsyncIterator, Callable

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI

from opspilot_api.config import Settings
from opspilot_api.main import create_app

ClientFactory = Callable[[FastAPI], httpx.AsyncClient]


ENVIRONMENT_SETTINGS = [
    "APP_ENV",
    "LOG_LEVEL",
    "DATABASE_URL",
    "REDIS_URL",
    "JWT_ISSUER",
    "JWT_AUDIENCE",
    "READINESS_TIMEOUT_SECONDS",
    "TRUSTED_PROXIES",
    "SSE_HEARTBEAT_SECONDS",
]


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests see only the settings they pass explicitly, never the developer's shell."""
    for name in ENVIRONMENT_SETTINGS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="test",
        database_url="postgresql+psycopg://user:pw@db.invalid:5432/opspilot",
        redis_url="redis://redis.invalid:6379/0",
        jwt_issuer="https://idp.invalid/realms/opspilot",
        jwt_audience="opspilot-api",
        rate_limit_enabled=False,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
