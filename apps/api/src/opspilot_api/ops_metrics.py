"""Process metrics behind the operational alerts (docs/operations/alerts.md).

The API exposes these at /metrics and the worker on WORKER_METRICS_PORT. The
alert rules in observability/rules/ are written against exactly these names,
so a rename here must be mirrored there (promtool tests catch it).
"""

from collections.abc import Iterable
from datetime import UTC, datetime

from prometheus_client import REGISTRY, Counter, Gauge, Histogram
from prometheus_client.core import GaugeMetricFamily, Metric
from prometheus_client.registry import Collector
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import QueuePool

from opspilot_api.db.models import (
    EventRelayCheckpoint,
    IncidentEvent,
    Investigation,
    InvestigationStatus,
    ProposalStatus,
    RemediationProposal,
)

AGENT_RUNS = Counter("opspilot_agent_runs", "Agent runs by final outcome", ["agent", "outcome"])
LLM_REQUESTS = Counter(
    "opspilot_llm_requests", "LLM completions by outcome", ["provider", "model", "outcome"]
)
LLM_TOKENS = Counter("opspilot_llm_tokens", "LLM tokens used", ["provider", "model", "direction"])
LLM_COST = Counter("opspilot_llm_cost_usd", "Estimated LLM spend in USD", ["provider", "model"])
LLM_DAILY_BUDGET = Gauge(
    "opspilot_llm_daily_budget_usd", "Configured LLM spend budget per 24 hours (USD)"
)
REMEDIATIONS = Counter(
    "opspilot_remediation_executions", "Finished remediation executions", ["action", "outcome"]
)
REMEDIATION_BLOCKED = Counter(
    "opspilot_remediation_blocked",
    "Executions refused by the pre-execution safety recheck",
    ["reason"],
)
QUEUE_DEPTH = Gauge("opspilot_queue_depth", "Jobs waiting to be picked up", ["queue"])
QUEUE_OLDEST = Gauge(
    "opspilot_queue_oldest_age_seconds", "Age of the oldest waiting job", ["queue"]
)
EVENT_DELAY = Histogram(
    "opspilot_event_processing_delay_seconds",
    "Time from an event occurring to its consumer finishing with it",
    ["consumer"],
    buckets=(0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 900),
)


def blocked_reason(problem: str) -> str:
    """A low-cardinality label for a recheck failure message."""
    for needle, reason in (
        ("no approval", "unapproved"),
        ("changed after it was approved", "stale_approval"),
        ("expired", "expired"),
        ("namespace", "namespace_not_allowed"),
    ):
        if needle in problem:
            return reason
    return "invalid_parameters"


class PoolCollector(Collector):
    """Checked-out vs. maximum connections of each tracked SQLAlchemy pool, read at scrape time."""

    def __init__(self) -> None:
        self._engines: dict[str, AsyncEngine] = {}

    def track(self, name: str, engine: AsyncEngine) -> None:
        self._engines[name] = engine

    def untrack(self, name: str) -> None:
        self._engines.pop(name, None)

    def collect(self) -> Iterable[Metric]:
        in_use = GaugeMetricFamily(
            "opspilot_db_pool_connections_in_use", "Connections checked out", labels=["pool"]
        )
        maximum = GaugeMetricFamily(
            "opspilot_db_pool_connections_max",
            "Most connections the pool will open (size + overflow)",
            labels=["pool"],
        )
        for name, engine in list(self._engines.items()):
            pool = engine.sync_engine.pool
            if not isinstance(pool, QueuePool):
                continue
            overflow = max(int(getattr(pool, "_max_overflow", 0)), 0)
            in_use.add_metric([name], pool.checkedout())
            maximum.add_metric([name], pool.size() + overflow)
        yield in_use
        yield maximum


POOLS = PoolCollector()
REGISTRY.register(POOLS)


async def sample_queues(
    sessions: async_sessionmaker[AsyncSession],
    *,
    outbox: bool = False,
    now: datetime | None = None,
) -> None:
    """Refresh the queue gauges: investigations, approved remediations, and the event outbox."""
    now = now or datetime.now(UTC)
    async with sessions() as session:
        queues = {
            "investigations": await session.execute(
                select(func.count(), func.min(Investigation.created_at)).where(
                    Investigation.status == InvestigationStatus.QUEUED
                )
            ),
            "remediations": await session.execute(
                select(func.count(), func.min(RemediationProposal.updated_at)).where(
                    RemediationProposal.status == ProposalStatus.APPROVED
                )
            ),
        }
        for queue, result in queues.items():
            count, oldest = result.one()
            QUEUE_DEPTH.labels(queue).set(count)
            QUEUE_OLDEST.labels(queue).set((now - oldest).total_seconds() if oldest else 0)
        if outbox:
            checkpoint = await session.scalar(select(func.max(EventRelayCheckpoint.last_sequence)))
            pending = await session.scalar(
                select(func.count()).where(IncidentEvent.sequence > (checkpoint or 0))
            )
            QUEUE_DEPTH.labels("event_outbox").set(pending or 0)
