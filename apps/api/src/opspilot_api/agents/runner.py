"""Runs queued investigations: claims a job, builds the tools, runs the workflow.

A crash leaves the job running with a lease; once the lease expires another
claim resumes it from its last persisted node (up to three attempts). While a
worker is alive it renews its lease, so slow model calls never let a second
worker take over a job that is still running; if the lease was lost anyway,
the run stops.
"""

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opspilot_api.agents.investigation import ContextFactory, Investigator
from opspilot_api.agents.queue import claim
from opspilot_api.agents.tools import ServiceTarget, ToolContext
from opspilot_api.db.models import Investigation, InvestigationStatus, Service
from opspilot_api.kube import KubeReader
from opspilot_api.ops_metrics import AGENT_RUNS
from opspilot_api.runbooks.embeddings import Embedder
from opspilot_api.telemetry import LogsProvider, MetricsProvider, TracesProvider

log = structlog.get_logger("opspilot.investigation")

LEASE = timedelta(minutes=10)


def context_factory(
    sessions: async_sessionmaker[AsyncSession],
    *,
    metrics: MetricsProvider,
    logs: LogsProvider,
    traces: TracesProvider,
    kube: KubeReader,
    embedder: Embedder | None,
    allowed_namespaces: frozenset[str],
    environment: str | None = None,
) -> ContextFactory:
    async def make(organization_id: uuid.UUID, incident_id: uuid.UUID) -> ToolContext:
        async def resolve(slug: str) -> ServiceTarget | None:
            async with sessions() as session:
                service = await session.scalar(
                    select(Service).where(
                        Service.organization_id == organization_id, Service.slug == slug
                    )
                )
            if service is None:
                return None
            return ServiceTarget(
                str(service.id),
                service.slug,
                service.name,
                service.namespace,
                service.deployment_name,
            )

        return ToolContext(
            organization_id=organization_id,
            now=datetime.now(UTC),
            resolve_service=resolve,
            metrics=metrics,
            logs=logs,
            traces=traces,
            kube=kube,
            allowed_namespaces=allowed_namespaces,
            sessions=sessions,
            embedder=embedder,
            incident_id=incident_id,
            environment=environment,
        )

    return make


class InvestigationRunner:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        new_investigator: Callable[[], Investigator],
    ) -> None:
        self.sessions = sessions
        self.new_investigator = new_investigator

    async def run_once(self) -> bool:
        """Claim and run one investigation. False when the queue is empty."""
        investigation = await claim(self.sessions, LEASE)
        if investigation is None:
            return False
        log.info(
            "investigation started",
            investigation_id=str(investigation.id),
            attempt=investigation.attempts,
        )
        work = asyncio.ensure_future(self.new_investigator().run(investigation.id))
        keeper = asyncio.create_task(
            self._keep_lease(investigation.id, investigation.attempts, work)
        )
        try:
            status = await work
        except asyncio.CancelledError:
            if keeper.done():  # we cancelled it: another worker owns the job now
                log.warning("investigation lease lost", investigation_id=str(investigation.id))
                return True
            raise
        except Exception:
            # Left running; the expired lease makes it claimable again (resumes at its last node).
            log.exception("investigation crashed", investigation_id=str(investigation.id))
            AGENT_RUNS.labels("investigation", "crashed").inc()
            return True
        finally:
            keeper.cancel()
        log.info(
            "investigation finished", investigation_id=str(investigation.id), status=status.value
        )
        return True

    async def _keep_lease(
        self, investigation_id: uuid.UUID, attempt: int, work: "asyncio.Future[Any]"
    ) -> None:
        """Renew the lease every third of its length while this attempt still owns the job."""
        lease = LEASE
        while not work.done():
            await asyncio.sleep(lease.total_seconds() / 3)
            async with self.sessions() as session:
                renewed = await session.execute(
                    update(Investigation)
                    .where(
                        Investigation.id == investigation_id,
                        Investigation.attempts == attempt,
                        Investigation.status == InvestigationStatus.RUNNING,
                    )
                    .values(lease_until=datetime.now(UTC) + lease)
                )
                await session.commit()
            if renewed.rowcount == 0 and not work.done():  # type: ignore[attr-defined]
                work.cancel()
                return
