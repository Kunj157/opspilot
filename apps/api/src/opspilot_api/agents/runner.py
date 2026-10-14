"""Runs queued investigations: claims a job, builds the tools, runs the workflow.

A crash leaves the job running with a lease; once the lease expires another
claim resumes it from its last persisted node (up to three attempts).
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opspilot_api.agents.investigation import ContextFactory, Investigator
from opspilot_api.agents.queue import claim
from opspilot_api.agents.tools import ServiceTarget, ToolContext
from opspilot_api.db.models import Service
from opspilot_api.kube import KubeReader
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
        try:
            status = await self.new_investigator().run(investigation.id)
        except Exception:
            # Left running; the expired lease makes it claimable again (resumes at its last node).
            log.exception("investigation crashed", investigation_id=str(investigation.id))
            return True
        log.info(
            "investigation finished", investigation_id=str(investigation.id), status=status.value
        )
        return True
