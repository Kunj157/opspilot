"""Investigation tools with fake telemetry and Kubernetes: validation, safety, evidence."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from opspilot_api.agents.tools import (
    ServiceTarget,
    ToolContext,
    run_tool,
)
from opspilot_api.kube import NamespaceNotAllowed, Revision, RolloutStatus, check_namespace
from opspilot_api.telemetry import (
    LogLine,
    Sample,
    Series,
    Span,
    TelemetryUnavailable,
    TraceDetail,
    TraceSummary,
)

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
CHECKOUT = ServiceTarget(
    id="svc-1", slug="checkout", name="Checkout", namespace="demo", deployment="checkout"
)
FOREIGN = ServiceTarget(
    id="svc-9", slug="dns", name="DNS", namespace="kube-system", deployment="coredns"
)


class Metrics:
    def __init__(self, down: bool = False) -> None:
        self.down = down
        self.queries: list[str] = []

    async def query(self, promql: str, at: datetime) -> list[Sample]:
        self.queries.append(promql)
        if self.down:
            raise TelemetryUnavailable("prometheus unreachable: ConnectError")
        before = at < NOW - timedelta(minutes=1)
        if "http_errors_total" in promql:
            return [] if before else [Sample({}, 0.45)]
        if "duration" in promql:
            return [Sample({}, 0.08 if before else 0.12)]
        return [Sample({}, 1.0)]

    async def query_range(
        self, promql: str, start: datetime, end: datetime, step: timedelta
    ) -> list[Series]:
        return []


class Logs:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, logql: str, start: datetime, end: datetime, limit: int) -> list[LogLine]:
        self.queries.append(logql)
        labels = {
            "service_name": "checkout",
            "level": "error",
            "route": "/orders",
            "status": "500",
            "trace_id": "abc",
        }
        return [LogLine(NOW, "request served", labels) for _ in range(3)]


class Traces:
    async def search(
        self, service: str, start: datetime, end: datetime, limit: int, *, errors_only: bool = False
    ) -> list[TraceSummary]:
        return [TraceSummary("t1", "storefront", "POST /api/checkout", NOW, 40.0)]

    async def get(self, trace_id: str) -> TraceDetail | None:
        return TraceDetail(
            trace_id,
            [
                Span(
                    "checkout",
                    "POST /orders",
                    "SPAN_KIND_SERVER",
                    12.0,
                    True,
                    {"error.type": "InjectedFault"},
                ),
                Span("payment", "POST /charge", "SPAN_KIND_SERVER", 3.0, False),
            ],
        )


class Kube:
    allowed = frozenset({"demo"})

    async def rollout_history(self, namespace: str, deployment: str) -> list[Revision]:
        check_namespace(namespace, self.allowed)
        return [
            Revision(
                4,
                NOW - timedelta(minutes=3),
                "release checkout 1.4.2 (checkout-http-500)",
                "1.4.2",
                "img",
            ),
            Revision(3, NOW - timedelta(days=1), None, "1.0.0", "img"),
        ]

    async def rollout_status(self, namespace: str, deployment: str) -> RolloutStatus:
        check_namespace(namespace, self.allowed)
        return RolloutStatus(2, 2, 2, 2, True, ["Available=True"])


def context(**overrides: Any) -> ToolContext:
    services = {"checkout": CHECKOUT, "dns": FOREIGN}

    async def resolve(slug: str) -> ServiceTarget | None:
        return services.get(slug)

    values: dict[str, Any] = {
        "organization_id": "org-1",
        "now": NOW,
        "resolve_service": resolve,
        "metrics": Metrics(),
        "logs": Logs(),
        "traces": Traces(),
        "kube": Kube(),
        "allowed_namespaces": frozenset({"demo"}),
    }
    values.update(overrides)
    return ToolContext(**values)


async def test_metrics_compare_now_with_the_baseline() -> None:
    metrics = Metrics()
    result = await run_tool(
        context(metrics=metrics), "query_service_metrics", {"service": "checkout"}
    )

    assert result.ok, result.error
    assert result.data["error_rate"] == pytest.approx(0.45)
    assert result.data["baseline_error_rate"] == 0.0
    assert "45.0%" in result.summary
    assert result.evidence is not None
    assert result.evidence.source == "prometheus"
    assert result.evidence.time_range_end == NOW
    assert all('namespace="demo"' in q and 'service="checkout"' in q for q in metrics.queries)


async def test_logs_summarise_errors_with_trace_ids() -> None:
    logs = Logs()
    result = await run_tool(context(logs=logs), "search_service_logs", {"service": "checkout"})

    assert result.data["error_lines"] == 3
    assert result.data["trace_ids"] == ["abc"]
    assert "status 500" in result.summary
    assert 'level="error"' in logs.queries[0]


async def test_trace_summary_names_the_failing_spans() -> None:
    result = await run_tool(context(), "get_trace_summary", {"service": "checkout"})

    assert result.data["failing_spans"] == [
        {"service": "checkout", "span": "POST /orders", "error_type": "InjectedFault"}
    ]
    assert result.evidence is not None
    assert result.evidence.source == "tempo"


async def test_recent_deployments_flag_a_release_in_the_window() -> None:
    result = await run_tool(context(), "get_recent_deployments", {"service": "checkout"})

    assert result.data["latest"]["version"] == "1.4.2"
    assert result.data["previous"]["version"] == "1.0.0"
    assert "1.4.2" in result.summary
    assert "3 minutes ago" in result.summary


async def test_rollout_status() -> None:
    result = await run_tool(context(), "get_kubernetes_rollout_status", {"service": "checkout"})

    assert result.data["complete"] is True
    assert "2/2 available" in result.summary


async def test_services_outside_allowed_namespaces_are_refused() -> None:
    result = await run_tool(context(), "get_recent_deployments", {"service": "dns"})

    assert not result.ok
    assert "not allowed" in (result.error or "")


async def test_unknown_services_and_bad_arguments_are_errors_not_exceptions() -> None:
    unknown = await run_tool(context(), "query_service_metrics", {"service": "warehouse"})
    extra = await run_tool(
        context(), "query_service_metrics", {"service": "checkout", "promql": "up"}
    )
    too_long = await run_tool(
        context(), "query_service_metrics", {"service": "checkout", "minutes": 10_000}
    )
    no_tool = await run_tool(context(), "execute_shell", {"command": "rm -rf /"})

    assert not unknown.ok
    assert "unknown service" in (unknown.error or "")
    assert not extra.ok
    assert "invalid arguments" in (extra.error or "")
    assert not too_long.ok
    assert not no_tool.ok
    assert "unknown tool" in (no_tool.error or "")


async def test_tools_outside_the_agent_allow_list_are_refused() -> None:
    result = await run_tool(
        context(),
        "get_recent_deployments",
        {"service": "checkout"},
        allowed={"query_service_metrics"},
    )

    assert not result.ok
    assert "not allowed for this agent" in (result.error or "")


async def test_backend_outages_become_failed_results() -> None:
    result = await run_tool(
        context(metrics=Metrics(down=True)), "query_service_metrics", {"service": "checkout"}
    )

    assert not result.ok
    assert "prometheus unreachable" in (result.error or "")


def test_namespace_check() -> None:
    with pytest.raises(NamespaceNotAllowed):
        check_namespace("kube-system", frozenset({"demo"}))
