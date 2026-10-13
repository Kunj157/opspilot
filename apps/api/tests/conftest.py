from collections.abc import AsyncIterator, Callable

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI

from opspilot_api.config import Settings
from opspilot_api.main import create_app

ClientFactory = Callable[[FastAPI], httpx.AsyncClient]


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="test",
        database_url="postgresql+psycopg://user:pw@db.invalid:5432/opspilot",
        redis_url="redis://redis.invalid:6379/0",
        jwt_issuer="https://idp.invalid/realms/opspilot",
        jwt_audience="opspilot-api",
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
