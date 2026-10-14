import json
import uuid

import httpx
import pytest
import structlog
from fastapi import FastAPI
from opentelemetry import trace

from opspilot_api.events.producer import trace_headers


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


TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
PARENT_SPAN_ID = "00f067aa0ba902b7"
TRACEPARENT = f"00-{TRACE_ID}-{PARENT_SPAN_ID}-01"


def request_log(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]
    entry: dict[str, object] = next(
        line for line in lines if line.get("message") == "request completed"
    )
    return entry


async def test_trace_context_from_traceparent_is_logged(
    client: httpx.AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    await client.get("/api/v1/health", headers={"traceparent": TRACEPARENT})

    entry = request_log(capsys)
    assert entry["trace_id"] == TRACE_ID
    assert entry["span_id"] == PARENT_SPAN_ID


@pytest.mark.parametrize(
    "bad",
    [
        "garbage",
        f"00-{'0' * 32}-{PARENT_SPAN_ID}-01",
        f"00-{TRACE_ID}-{'0' * 16}-01",
        f"00-{TRACE_ID[:-1]}z-{PARENT_SPAN_ID}-01",
    ],
)
async def test_malformed_traceparent_is_ignored(
    client: httpx.AsyncClient, capsys: pytest.CaptureFixture[str], bad: str
) -> None:
    response = await client.get("/api/v1/health", headers={"traceparent": bad})

    entry = request_log(capsys)
    assert response.status_code == 200
    assert "trace_id" not in entry
    assert "span_id" not in entry


async def test_without_trace_context_no_ids_are_logged(
    client: httpx.AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    await client.get("/api/v1/health")

    assert "trace_id" not in request_log(capsys)


async def test_an_active_span_wins_over_the_header(
    client: httpx.AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    active = trace.SpanContext(
        trace_id=0x1234, span_id=0x5678, is_remote=False, trace_flags=trace.TraceFlags(1)
    )

    with trace.use_span(trace.NonRecordingSpan(active)):
        await client.get("/api/v1/health", headers={"traceparent": TRACEPARENT})

    entry = request_log(capsys)
    assert entry["trace_id"] == f"{0x1234:032x}"
    assert entry["span_id"] == f"{0x5678:016x}"


async def test_trace_context_reaches_handler_logs_and_published_events(
    app: FastAPI, client: httpx.AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    async def probe() -> dict[str, str]:
        structlog.get_logger().info("inside handler")
        return {k: v.decode() for k, v in trace_headers()}

    app.add_api_route("/probe", probe)

    response = await client.get("/probe", headers={"traceparent": TRACEPARENT})

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]
    handler_log = next(line for line in lines if line.get("message") == "inside handler")
    assert handler_log["trace_id"] == TRACE_ID
    assert response.json()["traceparent"].startswith(f"00-{TRACE_ID}-")


async def test_trace_context_does_not_leak_between_requests(
    client: httpx.AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    await client.get("/api/v1/health", headers={"traceparent": TRACEPARENT})
    await client.get("/api/v1/health")

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]
    entries = [line for line in lines if line.get("message") == "request completed"]
    assert entries[0]["trace_id"] == TRACE_ID
    assert "trace_id" not in entries[1]
    assert not trace.get_current_span().get_span_context().is_valid
