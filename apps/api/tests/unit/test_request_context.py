import json
import uuid

import httpx
import pytest


async def test_generates_request_id_when_absent(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    request_id = response.headers["X-Request-ID"]
    assert uuid.UUID(request_id).version == 4


async def test_echoes_valid_incoming_request_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health", headers={"X-Request-ID": "abc-123_DEF.4"})

    assert response.headers["X-Request-ID"] == "abc-123_DEF.4"


@pytest.mark.parametrize("bad", ["x" * 129, "has space", "new\nline", "<script>", ""])
async def test_replaces_invalid_incoming_request_id(client: httpx.AsyncClient, bad: str) -> None:
    response = await client.get("/api/v1/health", headers={"X-Request-ID": bad})

    assert response.headers["X-Request-ID"] != bad
    assert uuid.UUID(response.headers["X-Request-ID"]).version == 4


async def test_request_log_is_structured_json(
    client: httpx.AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    response = await client.get("/api/v1/health", headers={"X-Request-ID": "req-42"})

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]
    entry = next(line for line in lines if line.get("message") == "request completed")
    assert response.status_code == 200
    assert entry["request_id"] == "req-42"
    assert entry["service"] == "api"
    assert entry["environment"] == "test"
    assert entry["level"] == "info"
    assert entry["method"] == "GET"
    assert entry["path"] == "/api/v1/health"
    assert entry["status_code"] == 200
    assert isinstance(entry["duration_ms"], float)
    assert "timestamp" in entry


async def test_request_context_does_not_leak_between_requests(
    client: httpx.AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    await client.get("/api/v1/health", headers={"X-Request-ID": "first"})
    await client.get("/api/v1/health")

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]
    ids = [line["request_id"] for line in lines if line.get("message") == "request completed"]
    assert ids[0] == "first"
    assert ids[1] != "first"
