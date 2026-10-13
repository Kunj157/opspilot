"""Prometheus, Loki, and Tempo adapters against canned upstream responses."""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from opspilot_api.telemetry import (
    LokiLogs,
    PrometheusMetrics,
    TelemetryUnavailable,
    TempoTraces,
    label_value,
)

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def transport(
    routes: dict[str, Any], seen: list[httpx.Request] | None = None
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        body = routes.get(request.url.path)
        if isinstance(body, Exception):
            raise body
        if isinstance(body, int):
            return httpx.Response(body)
        return httpx.Response(200 if body is not None else 404, json=body)

    return httpx.MockTransport(handler)


def test_label_values_are_escaped() -> None:
    assert label_value('a"b\\c\n') == '"a\\"b\\\\c\\n"'


async def test_prometheus_instant_query() -> None:
    seen: list[httpx.Request] = []
    metrics = PrometheusMetrics(
        "http://prom",
        transport=transport(
            {
                "/api/v1/query": {
                    "status": "success",
                    "data": {
                        "resultType": "vector",
                        "result": [{"metric": {"service": "checkout"}, "value": [1.0, "0.25"]}],
                    },
                }
            },
            seen,
        ),
    )

    samples = await metrics.query("up", at=NOW)

    assert [(s.labels, s.value) for s in samples] == [({"service": "checkout"}, 0.25)]
    assert seen[0].url.params["time"] == str(NOW.timestamp())


async def test_prometheus_range_query_and_nan() -> None:
    metrics = PrometheusMetrics(
        "http://prom",
        transport=transport(
            {
                "/api/v1/query_range": {
                    "status": "success",
                    "data": {
                        "resultType": "matrix",
                        "result": [
                            {"metric": {}, "values": [[1.0, "1"], [2.0, "NaN"], [3.0, "3"]]}
                        ],
                    },
                }
            }
        ),
    )

    series = await metrics.query_range(
        "x", NOW - timedelta(minutes=5), NOW, step=timedelta(seconds=15)
    )

    assert [p.value for p in series[0].points] == [1.0, 3.0]


@pytest.mark.parametrize(
    "failure",
    [
        500,
        httpx.ConnectError("refused"),
        httpx.ReadTimeout("slow"),
        {"status": "error", "error": "bad"},
    ],
)
async def test_prometheus_failures_are_reported_as_unavailable(failure: Any) -> None:
    metrics = PrometheusMetrics("http://prom", transport=transport({"/api/v1/query": failure}))

    with pytest.raises(TelemetryUnavailable, match="prometheus"):
        await metrics.query("up", at=NOW)


async def test_loki_search_returns_lines_newest_first() -> None:
    body = {
        "status": "success",
        "data": {
            "resultType": "streams",
            "result": [
                {
                    "stream": {"service_name": "checkout"},
                    "values": [["1791900000000000000", "older"], ["1791900001000000000", "newer"]],
                }
            ],
        },
    }
    logs = LokiLogs("http://loki", transport=transport({"/loki/api/v1/query_range": body}))

    lines = await logs.search(
        '{service_name="checkout"}', NOW - timedelta(minutes=5), NOW, limit=10
    )

    assert [line.line for line in lines] == ["newer", "older"]
    assert lines[0].labels == {"service_name": "checkout"}


async def test_tempo_search_and_get() -> None:
    search = {
        "traces": [
            {
                "traceID": "abc",
                "rootServiceName": "storefront",
                "rootTraceName": "POST /api/checkout",
                "startTimeUnixNano": "1791900000000000000",
                "durationMs": 42,
            }
        ]
    }
    trace = {
        "batches": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "payment"}}]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "name": "POST /charge",
                                "kind": "SPAN_KIND_SERVER",
                                "startTimeUnixNano": "1000000",
                                "endTimeUnixNano": "6000000",
                                "status": {"code": "STATUS_CODE_ERROR"},
                                "attributes": [
                                    {"key": "error.type", "value": {"stringValue": "InjectedFault"}}
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }
    traces = TempoTraces(
        "http://tempo", transport=transport({"/api/search": search, "/api/traces/abc": trace})
    )

    found = await traces.search("storefront", NOW - timedelta(minutes=5), NOW, limit=5)
    detail = await traces.get("abc")

    assert (found[0].trace_id, found[0].root_service, found[0].duration_ms) == (
        "abc",
        "storefront",
        42,
    )
    assert detail is not None
    span = detail.spans[0]
    assert (span.service, span.name, span.error, span.duration_ms) == (
        "payment",
        "POST /charge",
        True,
        5.0,
    )
    assert span.attributes == {"error.type": "InjectedFault"}


async def test_tempo_unknown_trace_is_none() -> None:
    traces = TempoTraces("http://tempo", transport=transport({}))

    assert await traces.get("missing") is None
