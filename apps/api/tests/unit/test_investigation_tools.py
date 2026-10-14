"""Investigation tools with fake telemetry and Kubernetes: validation, safety, evidence."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from opspilot_api.agents.tools import (
    ServiceTarget,
    ToolContext,
    run_tool,
)
from opspilot_api.kube import (
    ConfigMapInfo,
    NamespaceNotAllowed,
    Revision,
    RolloutStatus,
    check_namespace,
)
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
                env={
                    "SERVICE_VERSION": "1.4.2",
                    "FAULT_ERROR_RATE": "0.5",
                    "DB_PASSWORD": "[REDACTED]",
                },
                config_refs=("configmap/shop", "secret/db"),
                commit={
                    "sha": "9f2c1e7ab0d4c3e2f1a0b9c8d7e6f5a4b3c2d1e0",
                    "author": "Dana Developer",
                    "message": "Retry orders on 5xx\n\nLonger body",
                    "pull_request": "#42",
                },
            ),
            Revision(
                3,
                NOW - timedelta(days=1),
                None,
                "1.0.0",
                "img",
                env={"SERVICE_VERSION": "1.0.0", "FAULT_ERROR_RATE": "0", "LOG_LEVEL": "info"},
                config_refs=("configmap/shop",),
                commit={"sha": "1111111111aaaa", "author": "Sam", "message": "Initial release"},
            ),
        ]

    async def rollout_status(self, namespace: str, deployment: str) -> RolloutStatus:
        check_namespace(namespace, self.allowed)
        return RolloutStatus(2, 2, 2, 2, True, ["Available=True"])

    async def config_maps(self, namespace: str, names: list[str]) -> list[ConfigMapInfo]:
        check_namespace(namespace, self.allowed)
        return [
            ConfigMapInfo(n, NOW - timedelta(minutes=10), ("feature.flags",)) for n in names
        ] + [ConfigMapInfo("old", NOW - timedelta(days=3), ())]


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


async def test_configuration_changes_compare_the_latest_two_revisions() -> None:
    result = await run_tool(context(), "get_recent_configuration_changes", {"service": "checkout"})

    assert result.ok, result.error
    assert result.data["env_changes"] == [
        {"name": "DB_PASSWORD", "change": "added", "before": None, "after": "[REDACTED]"},
        {"name": "FAULT_ERROR_RATE", "change": "changed", "before": "0", "after": "0.5"},
        {"name": "LOG_LEVEL", "change": "removed", "before": "info", "after": None},
        {"name": "SERVICE_VERSION", "change": "changed", "before": "1.0.0", "after": "1.4.2"},
    ]
    assert result.data["references_added"] == ["secret/db"]
    assert [c["name"] for c in result.data["config_maps_updated"]] == ["shop"]
    assert "FAULT_ERROR_RATE 0 -> 0.5" in result.summary
    assert "now uses secret/db" in result.summary
    assert "configmap shop updated 10 minutes ago" in result.summary
    assert result.evidence is not None
    assert result.evidence.evidence_type == "configuration"


async def test_configuration_changes_refuse_services_outside_allowed_namespaces() -> None:
    result = await run_tool(context(), "get_recent_configuration_changes", {"service": "dns"})

    assert not result.ok
    assert "not allowed" in (result.error or "")


async def test_commit_metadata_names_the_commits_of_the_latest_two_revisions() -> None:
    result = await run_tool(context(), "get_commit_metadata", {"service": "checkout"})

    assert result.ok, result.error
    assert result.summary == (
        "Checkout revision 4 (1.4.2) was built from commit 9f2c1e7ab0d4 by Dana Developer: "
        "'Retry orders on 5xx' (#42); revision 3 ran commit 1111111111aa by Sam: "
        "'Initial release'"
    )
    assert result.data["commit"]["pull_request"] == "#42"
    assert result.data["previous_commit"]["sha"] == "1111111111aaaa"


async def test_commit_metadata_reports_missing_annotations_and_refuses_other_namespaces() -> None:
    class Bare(Kube):
        async def rollout_history(self, namespace: str, deployment: str) -> list[Revision]:
            return [Revision(2, NOW, None, "1.0.0", "img")]

    missing = await run_tool(context(kube=Bare()), "get_commit_metadata", {"service": "checkout"})
    foreign = await run_tool(context(), "get_commit_metadata", {"service": "dns"})

    assert missing.error == (
        "checkout revision 2 has no commit metadata (opspilot.io/commit-* pod template annotations)"
    )
    assert "not allowed" in (foreign.error or "")


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
