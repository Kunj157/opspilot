"""A lost database connection answers 503 with Retry-After, never a 500 with details."""

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from opspilot_api.db import errors


def app_raising(exc: Exception) -> FastAPI:
    app = FastAPI()
    errors.install(app)

    @app.get("/boom")
    async def boom() -> None:
        raise exc

    return app


@pytest.mark.parametrize(
    "exc",
    [
        OperationalError("SELECT 1", {}, Exception("connection refused to 10.0.0.5")),
        InterfaceError("SELECT 1", {}, Exception("connection closed")),
        PoolTimeoutError("QueuePool limit of size 5 overflow 10 reached"),
    ],
)
async def test_database_errors_become_503(exc: Exception) -> None:
    transport = httpx.ASGITransport(app=app_raising(exc))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == errors.RETRY_AFTER_SECONDS
    assert response.json() == {"detail": "Database unavailable, retry shortly"}
    assert "10.0.0.5" not in response.text
