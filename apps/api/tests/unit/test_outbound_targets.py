"""SSRF boundary: outbound hosts come from settings, never from request or model input.

The API makes no outbound call on a request's behalf. The worker calls
Prometheus, Loki, Tempo, and the LLM at addresses read from settings; values
from telemetry or model output only ever become query parameters or a
validated path segment on those hosts.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from opspilot_api.telemetry import LokiLogs, PrometheusMetrics, TempoTraces

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
HOSTILE = [
    "../../api/admin",
    "http://169.254.169.254/latest/meta-data/",
    "//evil.example/x",
    "@evil.example",
    "abc?target=http://evil.example",
    "abc#frag",
    "abc/../../x",
    "",
]


def recording(seen: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"status": "success", "data": {"result": []}})

    return httpx.MockTransport(handler)


@pytest.mark.parametrize("trace_id", HOSTILE)
async def test_a_hostile_trace_id_never_becomes_a_request(trace_id: str) -> None:
    seen: list[httpx.Request] = []
    traces = TempoTraces("http://tempo:3200", transport=recording(seen))

    assert await traces.get(trace_id) is None
    assert seen == []


@pytest.mark.parametrize("text", HOSTILE)
async def test_query_text_stays_a_parameter_on_the_configured_host(text: str) -> None:
    seen: list[httpx.Request] = []
    metrics = PrometheusMetrics("http://prom:9090", transport=recording(seen))
    logs = LokiLogs("http://loki:3100", transport=recording(seen))

    await metrics.query(text, at=NOW)
    await logs.search(text, start=NOW - timedelta(minutes=5), end=NOW, limit=10)

    assert [(r.url.host, r.url.port, r.url.path) for r in seen] == [
        ("prom", 9090, "/api/v1/query"),
        ("loki", 3100, "/loki/api/v1/query_range"),
    ]
    assert all(r.url.params["query"] == text for r in seen)


def _names(schema: Any, components: dict[str, Any], seen: set[str]) -> set[str]:
    """Every property name reachable from a JSON schema."""
    if isinstance(schema, list):
        return set().union(*(_names(s, components, seen) for s in schema)) if schema else set()
    if not isinstance(schema, dict):
        return set()
    names: set[str] = set()
    if ref := schema.get("$ref"):
        name = ref.rsplit("/", 1)[-1]
        if name in seen:
            return set()
        seen.add(name)
        return _names(components[name], components, seen)
    names.update(schema.get("properties", {}))
    for value in schema.values():
        names |= _names(value, components, seen)
    return names


def test_no_endpoint_accepts_an_outbound_address(app: FastAPI) -> None:
    """Only links for people take a URL (a runbook's source, a service's repository):
    validated as http(s), stored, and shown, never fetched (see the integration test)."""
    spec = app.openapi()
    components = spec.get("components", {}).get("schemas", {})
    inputs: set[str] = set()
    for operations in spec["paths"].values():
        for operation in operations.values():
            inputs |= {p["name"].lower() for p in operation.get("parameters", [])}
            body = operation.get("requestBody", {}).get("content", {})
            for media in body.values():
                inputs |= {n.lower() for n in _names(media.get("schema", {}), components, set())}

    url_like = {n for n in inputs if any(k in n for k in ("url", "uri", "host", "endpoint"))}
    assert url_like == {"source_url", "repository_url"}
