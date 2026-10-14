"""Read-only investigation tools: plain application functions, tested without a model.

Agents never write queries. Every tool takes a catalog service (and small
bounded parameters), builds its own query, enforces the namespace
allow-list, and returns a summary plus evidence that cites its source,
query, and time range. Failures are results, never exceptions, so an
investigation can continue with what it has.
"""

import asyncio
import contextlib
import json
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opspilot_api.db.models import Incident, Runbook, RunbookStatus, Service, ServiceDependency
from opspilot_api.kube import KubeReader, NamespaceNotAllowed
from opspilot_api.runbooks.document import RunbookDocumentError, parse
from opspilot_api.runbooks.embeddings import Embedder
from opspilot_api.runbooks.retrieval import looks_like_injection, search, untrusted_context
from opspilot_api.telemetry import (
    LogsProvider,
    MetricsProvider,
    TelemetryUnavailable,
    TracesProvider,
    label_value,
)

TOOL_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True)
class ServiceTarget:
    id: str
    slug: str
    name: str
    namespace: str | None
    deployment: str | None


@dataclass(frozen=True)
class EvidenceDraft:
    evidence_type: str
    source: str
    summary: str
    query: str | None
    time_range_start: datetime | None
    time_range_end: datetime | None
    confidence: float
    content: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResult:
    tool: str
    ok: bool
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    evidence: EvidenceDraft | None = None
    error: str | None = None


@dataclass
class ToolContext:
    organization_id: uuid.UUID | str
    now: datetime
    resolve_service: Callable[[str], Awaitable[ServiceTarget | None]]
    metrics: MetricsProvider
    logs: LogsProvider
    traces: TracesProvider
    kube: KubeReader
    allowed_namespaces: frozenset[str]
    sessions: async_sessionmaker[AsyncSession] | None = None
    embedder: Embedder | None = None
    incident_id: uuid.UUID | None = None


class ToolFailure(Exception):
    """An expected failure, reported to the agent as a failed result."""


class ServiceArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: str = Field(min_length=1, max_length=63, pattern=r"^[a-z0-9-]+$")


class WindowArgs(ServiceArgs):
    minutes: int = Field(default=15, ge=1, le=180)


class RunbookArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=3, max_length=300)
    service: str | None = Field(default=None, max_length=63, pattern=r"^[a-z0-9-]+$")


class GetRunbookArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # A slug (as cited by search_runbooks) or a runbook ID.
    runbook: str = Field(min_length=2, max_length=63, pattern=r"^[a-z0-9-]+$")
    version: int | None = Field(default=None, ge=1)


# The full text handed to a model is bounded; sections are cut, never dropped silently.
RUNBOOK_MAX_CHARS = 6000


async def _target(ctx: ToolContext, slug: str, *, needs_workload: bool = True) -> ServiceTarget:
    target = await ctx.resolve_service(slug)
    if target is None:
        raise ToolFailure(f"unknown service {slug!r}")
    if needs_workload:
        if not target.namespace or not target.deployment:
            raise ToolFailure(f"{slug} has no namespace and deployment in the catalog")
        if target.namespace not in ctx.allowed_namespaces:
            raise ToolFailure(f"namespace {target.namespace!r} is not allowed for investigations")
    return target


def _selector(target: ServiceTarget) -> str:
    namespace = label_value(target.namespace or "")
    return f"namespace={namespace},service={label_value(target.deployment or '')}"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


async def _scalar(ctx: ToolContext, promql: str, at: datetime) -> float | None:
    samples = await ctx.metrics.query(promql, at)
    return samples[0].value if samples else None


async def query_service_metrics(ctx: ToolContext, args: WindowArgs) -> ToolResult:
    target = await _target(ctx, args.service)
    sel = _selector(target)
    queries = {
        "requests": f"sum(rate(http_requests_total{{{sel}}}[1m]))",
        "errors": f"sum(rate(http_errors_total{{{sel}}}[1m]))",
        "p95": "histogram_quantile(0.95, sum by (le) "
        f"(rate(http_request_duration_seconds_bucket{{{sel}}}[1m])))",
    }
    baseline_at = ctx.now - timedelta(minutes=args.minutes)
    now_values = await asyncio.gather(*(_scalar(ctx, q, ctx.now) for q in queries.values()))
    before = await asyncio.gather(*(_scalar(ctx, q, baseline_at) for q in queries.values()))
    rps, errors, p95 = now_values
    rps_before, errors_before, p95_before = before
    rate = (errors or 0.0) / rps if rps else None
    rate_before = (errors_before or 0.0) / rps_before if rps_before else None
    summary = (
        f"{target.name}: error rate {_pct(rate)} "
        f"(baseline {args.minutes} min ago {_pct(rate_before)}), {rps or 0:.2f} req/s, "
        f"p95 {(p95 or 0) * 1000:.0f} ms (was {(p95_before or 0) * 1000:.0f} ms)"
    )
    data = {
        "error_rate": rate,
        "baseline_error_rate": rate_before,
        "requests_per_second": rps,
        "p95_seconds": p95,
        "baseline_p95_seconds": p95_before,
    }
    return ToolResult(
        "query_service_metrics",
        True,
        summary,
        data,
        EvidenceDraft(
            "metrics",
            "prometheus",
            summary,
            json.dumps(queries),
            baseline_at,
            ctx.now,
            0.9 if rps is not None else 0.3,
            data,
        ),
    )


async def search_service_logs(ctx: ToolContext, args: WindowArgs) -> ToolResult:
    target = await _target(ctx, args.service)
    logql = (
        f"{{k8s_namespace_name={label_value(target.namespace or '')},"
        f'service_name={label_value(target.deployment or "")}}} | level="error"'
    )
    start = ctx.now - timedelta(minutes=args.minutes)
    lines = await ctx.logs.search(logql, start, ctx.now, 100)
    messages: Counter[str] = Counter()
    trace_ids: list[str] = []
    for line in lines:
        # Fields arrive as structured metadata (stream labels); a JSON body is also accepted.
        entry: dict[str, Any] = {**line.labels, "message": line.line[:200]}
        if line.line.startswith("{"):
            with contextlib.suppress(ValueError):
                entry.update(json.loads(line.line))
        where = f"{entry.get('route', '?')}, status {entry.get('status', '?')}"
        key = f"{entry.get('message', '')} ({where})"
        messages[key] += 1
        if (tid := entry.get("trace_id")) and tid not in trace_ids:
            trace_ids.append(tid)
    top = [{"message": m, "count": c} for m, c in messages.most_common(3)]
    summary = f"{len(lines)} error log lines from {target.name} in the last {args.minutes} min" + (
        ": " + "; ".join(f"{t['count']} x {t['message']}" for t in top) if top else ""
    )
    data = {"error_lines": len(lines), "top_messages": top, "trace_ids": trace_ids[:5]}
    return ToolResult(
        "search_service_logs",
        True,
        summary,
        data,
        EvidenceDraft("logs", "loki", summary, logql, start, ctx.now, 0.8 if lines else 0.4, data),
    )


async def get_trace_summary(ctx: ToolContext, args: WindowArgs) -> ToolResult:
    target = await _target(ctx, args.service)
    start = ctx.now - timedelta(minutes=args.minutes)
    found = await ctx.traces.search(
        target.deployment or target.slug, start, ctx.now, 5, errors_only=True
    )
    if not found:
        summary = f"No error traces for {target.name} in the last {args.minutes} min"
        return ToolResult(
            "get_trace_summary",
            True,
            summary,
            {"error_traces": 0},
            EvidenceDraft(
                "traces",
                "tempo",
                summary,
                f"service={target.slug} status=error",
                start,
                ctx.now,
                0.5,
            ),
        )
    detail = await ctx.traces.get(found[0].trace_id)
    failing = [
        {
            "service": s.service,
            "span": s.name,
            "error_type": s.attributes.get("error.type", "unknown"),
        }
        for s in (detail.spans if detail else [])
        if s.error and s.kind == "SPAN_KIND_SERVER"
    ]
    summary = (
        f"{len(found)} error traces for {target.name}; trace {found[0].trace_id} fails in "
        + (
            ", ".join(f"{f['service']} {f['span']} ({f['error_type']})" for f in failing)
            or "an unknown span"
        )
    )
    data = {"error_traces": len(found), "trace_id": found[0].trace_id, "failing_spans": failing}
    return ToolResult(
        "get_trace_summary",
        True,
        summary,
        data,
        EvidenceDraft(
            "traces",
            "tempo",
            summary,
            f"service={target.slug} status=error",
            start,
            ctx.now,
            0.85,
            data,
        ),
    )


def _ago(now: datetime, then: datetime | None) -> str:
    if then is None:
        return "at an unknown time"
    minutes = int((now - then).total_seconds() // 60)
    if minutes < 120:
        return f"{minutes} minutes ago"
    return f"{minutes // 60} hours ago"


async def get_recent_deployments(ctx: ToolContext, args: ServiceArgs) -> ToolResult:
    target = await _target(ctx, args.service)
    revisions = await ctx.kube.rollout_history(target.namespace or "", target.deployment or "")
    if not revisions:
        raise ToolFailure(f"no rollout history for {target.slug}")
    latest = revisions[0]
    previous = revisions[1] if len(revisions) > 1 else None

    def describe(r: Any) -> dict[str, Any]:
        return {
            "revision": r.revision,
            "version": r.version,
            "change_cause": r.change_cause,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }

    before, after = await _errors_around(ctx, target, latest.created_at)
    summary = (
        f"{target.name} revision {latest.revision} (version {latest.version}) rolled out "
        f"{_ago(ctx.now, latest.created_at)}"
        + (f": {latest.change_cause}" if latest.change_cause else "")
        + (
            f"; previous revision {previous.revision} ran version {previous.version}"
            if previous
            else ""
        )
        + f"; error rate before that rollout {_pct(before)}, now {_pct(after)}"
    )
    data = {
        "latest": describe(latest),
        "previous": describe(previous) if previous else None,
        "error_rate_before_latest": before,
        "error_rate_now": after,
    }
    return ToolResult(
        "get_recent_deployments",
        True,
        summary,
        data,
        EvidenceDraft(
            "deployment",
            "kubernetes",
            summary,
            f"rollout history deployment/{target.deployment}",
            latest.created_at,
            ctx.now,
            0.95,
            data,
        ),
    )


async def _error_rate(ctx: ToolContext, target: ServiceTarget, at: datetime) -> float | None:
    """Error rate over the 2 minutes ending at `at`."""
    sel = _selector(target)
    rps = await _scalar(ctx, f"sum(rate(http_requests_total{{{sel}}}[2m]))", at)
    if not rps:
        return None
    errors = await _scalar(ctx, f"sum(rate(http_errors_total{{{sel}}}[2m]))", at)
    return (errors or 0.0) / rps


async def _errors_around(
    ctx: ToolContext, target: ServiceTarget, rolled_out: datetime | None
) -> tuple[float | None, float | None]:
    """Error rate in the 2 minutes before the latest rollout started, and now. None when unknown."""
    try:
        before = await _error_rate(ctx, target, rolled_out) if rolled_out else None
        after = await _error_rate(ctx, target, ctx.now)
    except TelemetryUnavailable:
        return None, None
    return before, after


async def get_kubernetes_rollout_status(ctx: ToolContext, args: ServiceArgs) -> ToolResult:
    target = await _target(ctx, args.service)
    status = await ctx.kube.rollout_status(target.namespace or "", target.deployment or "")
    summary = (
        f"{target.name} rollout {'complete' if status.complete else 'in progress'}: "
        f"{status.available}/{status.desired} available, {status.updated} updated"
    )
    data = {
        "complete": status.complete,
        "desired": status.desired,
        "available": status.available,
        "updated": status.updated,
        "conditions": status.conditions,
    }
    return ToolResult(
        "get_kubernetes_rollout_status",
        True,
        summary,
        data,
        EvidenceDraft(
            "deployment",
            "kubernetes",
            summary,
            f"rollout status deployment/{target.deployment}",
            ctx.now,
            ctx.now,
            0.95,
            data,
        ),
    )


def _sessions(ctx: ToolContext) -> async_sessionmaker[AsyncSession]:
    if ctx.sessions is None:
        raise ToolFailure("this tool needs the database")
    return ctx.sessions


async def get_service_dependencies(ctx: ToolContext, args: ServiceArgs) -> ToolResult:
    target = await _target(ctx, args.service, needs_workload=False)
    async with _sessions(ctx)() as session:
        services = {
            s.id: s
            for s in await session.scalars(
                select(Service).where(Service.organization_id == ctx.organization_id)
            )
        }
        edges = (
            await session.execute(
                select(
                    ServiceDependency.source_service_id, ServiceDependency.target_service_id
                ).where(ServiceDependency.organization_id == ctx.organization_id)
            )
        ).all()
    me = uuid.UUID(str(target.id))
    calls = [services[t] for s, t in edges if s == me and t in services]
    callers = [services[s] for s, t in edges if t == me and s in services]

    def names(items: list[Service]) -> str:
        return ", ".join(f"{s.slug} ({s.health_status.value})" for s in items) or "none"

    summary = f"{target.name} calls {names(calls)}; called by {names(callers)}"
    data = {
        "calls": [{"service": s.slug, "health": s.health_status.value} for s in calls],
        "called_by": [{"service": s.slug, "health": s.health_status.value} for s in callers],
    }
    return ToolResult(
        "get_service_dependencies",
        True,
        summary,
        data,
        EvidenceDraft(
            "topology",
            "service catalog",
            summary,
            f"dependencies of {target.slug}",
            None,
            ctx.now,
            0.9,
            data,
        ),
    )


async def search_runbooks(ctx: ToolContext, args: RunbookArgs) -> ToolResult:
    if ctx.embedder is None:
        raise ToolFailure("runbook search is not configured")
    async with _sessions(ctx)() as session:
        hits = await search(
            session,
            ctx.embedder,
            organization_id=uuid.UUID(str(ctx.organization_id)),
            query=args.query,
            service=args.service,
            limit=4,
        )
    if not hits:
        raise ToolFailure("no runbook matched")
    runbooks: dict[str, dict[str, Any]] = {}
    for hit in hits:
        runbooks.setdefault(
            hit.runbook_slug,
            {
                "slug": hit.runbook_slug,
                "title": hit.title,
                "version": hit.version,
                "runbook_id": str(hit.runbook_id),
                "score": hit.score,
                "source_url": hit.source_url,
            },
        )
    summary = "Runbooks: " + "; ".join(
        f"{r['title']} v{r['version']} ({r['score']:.2f})" for r in runbooks.values()
    )
    data = {
        "runbooks": list(runbooks.values()),
        # Untrusted text, quoted for the model; never instructions.
        "excerpts": untrusted_context(
            [(h.runbook_slug, h.version, h.heading, h.content, h.flagged) for h in hits]
        ),
        "flagged": any(h.flagged for h in hits),
    }
    return ToolResult(
        "search_runbooks",
        True,
        summary,
        data,
        EvidenceDraft(
            "runbook", "runbook library", summary, args.query, None, ctx.now, hits[0].score, data
        ),
    )


async def get_runbook(ctx: ToolContext, args: GetRunbookArgs) -> ToolResult:
    by_id: uuid.UUID | None = None
    with contextlib.suppress(ValueError):
        by_id = uuid.UUID(args.runbook)
    async with _sessions(ctx)() as session:
        runbook = await session.scalar(
            select(Runbook).where(
                Runbook.organization_id == ctx.organization_id,
                Runbook.status == RunbookStatus.ACTIVE,
                Runbook.id == by_id if by_id else Runbook.slug == args.runbook,
            )
        )
    if runbook is None:
        raise ToolFailure(f"no active runbook {args.runbook!r}")
    if args.version is not None and args.version != runbook.version:
        raise ToolFailure(
            f"{runbook.slug} v{args.version} is not available; the current version is "
            f"v{runbook.version}"
        )
    try:
        sections = parse(runbook.content).sections
    except RunbookDocumentError as exc:
        raise ToolFailure(f"{runbook.slug} cannot be read: {exc}") from exc
    budget = RUNBOOK_MAX_CHARS // max(len(sections), 1)
    quoted = [
        (runbook.slug, runbook.version, s.heading, s.body[:budget], looks_like_injection(s.body))
        for s in sections
    ]
    flagged = [heading for _, _, heading, _, f in quoted if f]
    summary = (
        f"Runbook {runbook.title} v{runbook.version}: {len(sections)} sections ("
        + ", ".join(s.heading for s in sections)
        + ")"
        + (f"; flagged sections: {', '.join(flagged)}" if flagged else "")
    )
    data = {
        "runbook": {
            "slug": runbook.slug,
            "title": runbook.title,
            "version": runbook.version,
            "runbook_id": str(runbook.id),
            "source_url": runbook.source_url,
            "services": runbook.services,
        },
        "sections": [s.heading for s in sections],
        # Untrusted text, quoted for the model; never instructions.
        "content": untrusted_context(quoted),
        "flagged": bool(flagged),
    }
    return ToolResult(
        "get_runbook",
        True,
        summary,
        data,
        EvidenceDraft(
            "runbook",
            "runbook library",
            summary,
            f"runbook {runbook.slug} v{runbook.version}",
            None,
            ctx.now,
            0.9,
            data,
        ),
    )


async def search_similar_incidents(ctx: ToolContext, args: ServiceArgs) -> ToolResult:
    target = await _target(ctx, args.service, needs_workload=False)
    async with _sessions(ctx)() as session:
        rows = list(
            await session.scalars(
                select(Incident)
                .where(
                    Incident.organization_id == ctx.organization_id,
                    Incident.service_id == uuid.UUID(str(target.id)),
                    Incident.started_at >= ctx.now - timedelta(days=30),
                    *([Incident.id != ctx.incident_id] if ctx.incident_id else []),
                )
                .order_by(Incident.started_at.desc())
                .limit(5)
            )
        )
    items = [
        {
            "id": str(i.id),
            "title": i.title,
            "status": i.status.value,
            "started_at": i.started_at.isoformat(),
        }
        for i in rows
    ]
    summary = f"{len(items)} earlier incidents on {target.name} in 30 days" + (
        ": " + "; ".join(f"{i['title']} ({i['status'].lower()})" for i in items[:3])
        if items
        else ""
    )
    return ToolResult(
        "search_similar_incidents",
        True,
        summary,
        {"incidents": items},
        EvidenceDraft(
            "history",
            "incident history",
            summary,
            f"incidents on {target.slug}, 30 days",
            ctx.now - timedelta(days=30),
            ctx.now,
            0.6,
            {"incidents": items},
        ),
    )


ToolFunction = Callable[[ToolContext, Any], Awaitable[ToolResult]]

TOOLS: dict[str, tuple[type[BaseModel], ToolFunction, str]] = {
    "query_service_metrics": (
        WindowArgs,
        query_service_metrics,
        "Error rate, traffic, and p95 latency now vs a baseline",
    ),
    "search_service_logs": (
        WindowArgs,
        search_service_logs,
        "Recent error log lines, grouped, with trace IDs",
    ),
    "get_trace_summary": (WindowArgs, get_trace_summary, "Where recent error traces fail"),
    "get_service_dependencies": (
        ServiceArgs,
        get_service_dependencies,
        "What the service calls and what calls it",
    ),
    "get_recent_deployments": (
        ServiceArgs,
        get_recent_deployments,
        "Latest rollout revisions with versions and causes",
    ),
    "get_kubernetes_rollout_status": (
        ServiceArgs,
        get_kubernetes_rollout_status,
        "Current rollout progress",
    ),
    "search_runbooks": (
        RunbookArgs,
        search_runbooks,
        "Runbook sections matching symptoms (untrusted text)",
    ),
    "get_runbook": (
        GetRunbookArgs,
        get_runbook,
        "The full text of one runbook by slug, current version (untrusted text)",
    ),
    "search_similar_incidents": (
        ServiceArgs,
        search_similar_incidents,
        "Earlier incidents on the same service",
    ),
}


async def run_tool(
    ctx: ToolContext, name: str, arguments: dict[str, Any], *, allowed: set[str] | None = None
) -> ToolResult:
    """Validate and run one tool call. Never raises for expected failures."""
    if name not in TOOLS:
        return ToolResult(name, False, "", error=f"unknown tool {name!r}")
    if allowed is not None and name not in allowed:
        return ToolResult(name, False, "", error=f"tool {name!r} is not allowed for this agent")
    schema, function, _ = TOOLS[name]
    try:
        args = schema.model_validate(arguments)
    except ValidationError as exc:
        return ToolResult(name, False, "", error=f"invalid arguments: {exc.error_count()} errors")
    try:
        return await asyncio.wait_for(function(ctx, args), TOOL_TIMEOUT_SECONDS)
    except (ToolFailure, NamespaceNotAllowed, TelemetryUnavailable) as exc:
        return ToolResult(name, False, "", error=str(exc))
    except TimeoutError:
        return ToolResult(name, False, "", error=f"{name} timed out")
