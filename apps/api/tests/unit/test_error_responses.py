"""Error responses do not reveal internals (plan §25)."""

import json
from collections.abc import AsyncIterator

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

SECRET_DETAIL = "connection to postgresql://opspilot@db-primary.internal:5432 failed"


@pytest.fixture
async def failing_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async def boom() -> None:
        raise RuntimeError(SECRET_DETAIL)

    async def broken_stream() -> StreamingResponse:
        async def chunks() -> AsyncIterator[bytes]:
            yield b"partial"
            raise RuntimeError(SECRET_DETAIL)

        return StreamingResponse(chunks())

    app.add_api_route("/boom", boom)
    app.add_api_route("/broken-stream", broken_stream)
    async with LifespanManager(app) as manager:
        # Like a real server: the client gets the response, not the exception.
        transport = httpx.ASGITransport(app=manager.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def test_unhandled_errors_return_a_generic_body_with_the_request_id(
    failing_client: httpx.AsyncClient,
) -> None:
    response = await failing_client.get("/boom", headers={"X-Request-ID": "req-500"})

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error", "request_id": "req-500"}
    assert response.headers["X-Request-ID"] == "req-500"
    assert "postgresql" not in response.text
    assert "Traceback" not in response.text


async def test_the_details_go_to_the_log_with_the_request_id(
    failing_client: httpx.AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    await failing_client.get("/boom", headers={"X-Request-ID": "req-501"})

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]
    error = next(line for line in lines if line.get("message") == "unhandled error")
    completed = next(line for line in lines if line.get("message") == "request completed")
    assert error["request_id"] == "req-501"
    assert error["level"] == "error"
    assert "RuntimeError" in error["exception"]
    assert completed["status_code"] == 500


async def test_a_stream_that_fails_midway_is_cut_off_not_rewritten(
    failing_client: httpx.AsyncClient,
) -> None:
    response = await failing_client.get("/broken-stream")

    assert response.status_code == 200
    assert "postgresql" not in response.text


@pytest.mark.parametrize(("path", "status"), [("/api/v1/nope", 404), ("/api/v1/incidents", 401)])
async def test_client_errors_carry_no_internals(
    failing_client: httpx.AsyncClient, path: str, status: int
) -> None:
    response = await failing_client.get(path)

    assert response.status_code == status
    assert set(response.json()) == {"detail"}
