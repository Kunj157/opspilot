"""The detection worker: evaluates every watched service against Prometheus.

    opspilot-worker   (DATABASE_URL and PROMETHEUS_URL required)

Each cycle reads request and error rates for all services that have a
namespace and deployment in the catalog, feeds the rule, persists the rule
state, and applies the decision. A Prometheus outage skips the cycle
without changing anything.
"""

import asyncio
import time
import uuid
from datetime import datetime, timedelta

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opspilot_api.agents.queue import enqueue
from opspilot_api.db.models import (
    DetectorCheckpoint,
    HealthStatus,
    IncidentStatus,
    Service,
    ServiceDependency,
)
from opspilot_api.detection.rules import Decision, DetectorState, ErrorRateRule, Outcome, Window
from opspilot_api.detection.service import apply_decision, apply_impact
from opspilot_api.telemetry import MetricsProvider, TelemetryUnavailable

log = structlog.get_logger("opspilot.detection")

CYCLES = Counter("opspilot_detection_cycles", "Detection cycles by outcome", ["outcome"])
CYCLE_SECONDS = Histogram("opspilot_detection_cycle_seconds", "Duration of a detection cycle")
DECISIONS = Counter(
    "opspilot_detection_decisions", "Detector decisions other than none", ["detector", "outcome"]
)

RATE_WINDOW = "1m"
REQUESTS = f"sum by (namespace, service) (rate(http_requests_total[{RATE_WINDOW}]))"
ERRORS = f"sum by (namespace, service) (rate(http_errors_total[{RATE_WINDOW}]))"


class DetectionWorker:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        metrics: MetricsProvider,
        *,
        rule: ErrorRateRule | None = None,
        lag: timedelta = timedelta(seconds=30),
        auto_investigate: bool = False,
    ) -> None:
        self.sessions = sessions
        self.metrics = metrics
        self.rule = rule or ErrorRateRule()
        # Evaluate slightly in the past so late scrapes are already in.
        self.lag = lag
        # Queue an agent investigation for every new detector incident.
        self.auto_investigate = auto_investigate

    async def _rates(self, at: datetime) -> dict[tuple[str, str], Window]:
        requests, errors = await asyncio.gather(
            self.metrics.query(REQUESTS, at), self.metrics.query(ERRORS, at)
        )
        error_rates = {
            (s.labels.get("namespace"), s.labels.get("service")): s.value for s in errors
        }
        windows = {}
        for sample in requests:
            key = (sample.labels.get("namespace", ""), sample.labels.get("service", ""))
            rps = sample.value
            failed = error_rates.get(key, 0.0)  # no error series until the first error
            windows[key] = Window(requests_per_second=rps, error_rate=failed / rps if rps else 0.0)
        return windows

    async def cycle(self, now: datetime) -> str:
        """Evaluate every watched service once. Returns the cycle outcome."""
        start = time.perf_counter()
        at = now - self.lag
        try:
            windows = await self._rates(at)
        except TelemetryUnavailable as exc:
            log.warning("detection cycle skipped", reason=str(exc))
            CYCLES.labels("telemetry_unavailable").inc()
            return "telemetry_unavailable"

        async with self.sessions() as session:
            services = {
                s.id: s
                for s in await session.scalars(
                    select(Service).where(
                        Service.namespace.is_not(None), Service.deployment_name.is_not(None)
                    )
                )
            }
            edges = (
                await session.execute(
                    select(ServiceDependency.source_service_id, ServiceDependency.target_service_id)
                )
            ).all()
        calls: dict[uuid.UUID, list[uuid.UUID]] = {}
        for source, target in edges:
            calls.setdefault(source, []).append(target)

        # Phase 1: evaluate every service and persist its rule state.
        evaluated: dict[uuid.UUID, tuple[Decision, bool]] = {}
        healthy: list[uuid.UUID] = []
        for service in services.values():
            window = windows.get(
                (service.namespace or "", service.deployment_name or ""),
                Window(requests_per_second=None, error_rate=None),
            )
            evaluated[service.id] = await self._evaluate(service.id, window)
            decision, active = evaluated[service.id]
            if not active and decision.outcome is Outcome.NONE and self._has_traffic(window):
                healthy.append(service.id)
        failing = {sid for sid, (_, active) in evaluated.items() if active}
        await self._mark_healthy(healthy)

        # Phase 2: causes before symptoms, so a caller's impact lands on the
        # incident of the dependency that is actually failing.
        causes = {sid: self._cause(sid, calls, failing) for sid in services}
        ordered = sorted(services, key=lambda sid: causes[sid] is not None)
        for sid in ordered:
            decision, _ = evaluated[sid]
            if decision.outcome is not Outcome.NONE:
                await self._apply(sid, decision, causes[sid], at)
        CYCLES.labels("ok").inc()
        CYCLE_SECONDS.observe(time.perf_counter() - start)
        return "ok"

    def _has_traffic(self, window: Window) -> bool:
        return (window.requests_per_second or 0.0) >= self.rule.min_requests_per_second

    async def _mark_healthy(self, service_ids: list[uuid.UUID]) -> None:
        """Services with real traffic and nothing wrong; only changed rows are written."""
        if not service_ids:
            return
        async with self.sessions() as session:
            await session.execute(
                update(Service)
                .where(Service.id.in_(service_ids), Service.health_status != HealthStatus.HEALTHY)
                .values(health_status=HealthStatus.HEALTHY)
            )
            await session.commit()

    @staticmethod
    def _cause(
        service_id: uuid.UUID, calls: dict[uuid.UUID, list[uuid.UUID]], failing: set[uuid.UUID]
    ) -> uuid.UUID | None:
        """The deepest failing service this one depends on, if any."""
        cause = None
        seen = {service_id}
        frontier = [service_id]
        while frontier:
            current = frontier.pop()
            for target in calls.get(current, []):
                if target in seen:
                    continue
                seen.add(target)
                if target in failing:
                    cause = target
                frontier.append(target)
        return cause

    async def _evaluate(self, service_id: uuid.UUID, window: Window) -> tuple[Decision, bool]:
        async with self.sessions() as session:
            checkpoint = await session.get(
                DetectorCheckpoint, (service_id, self.rule.name), with_for_update=True
            )
            state = (
                DetectorState.model_validate(checkpoint.state) if checkpoint else DetectorState()
            )
            state, decision = self.rule.evaluate(state, window)
            if checkpoint is None:
                session.add(
                    DetectorCheckpoint(
                        service_id=service_id, detector=self.rule.name, state=state.model_dump()
                    )
                )
            else:
                checkpoint.state = state.model_dump()
            await session.commit()
        return decision, state.active

    async def _apply(
        self, service_id: uuid.UUID, decision: Decision, cause_id: uuid.UUID | None, at: datetime
    ) -> None:
        # One transaction per service, so one failure cannot block the others.
        window = {"window_start": at - timedelta(minutes=1), "window_end": at}
        async with self.sessions() as session:
            service = await session.get_one(Service, service_id, with_for_update=True)
            if cause_id is None:
                incident = await apply_decision(session, service, self.rule, decision, **window)
                if (
                    self.auto_investigate
                    and incident is not None
                    and incident.status is IncidentStatus.DETECTED
                ):
                    await enqueue(session, incident, f"detector:{self.rule.name}")
            else:
                cause = await session.get_one(Service, cause_id)
                incident = await apply_impact(
                    session, service, self.rule, decision, cause=cause, **window
                )
            await session.commit()
        DECISIONS.labels(self.rule.name, decision.outcome.value).inc()
        log.info(
            "detector decision",
            detector=self.rule.name,
            outcome=decision.outcome.value,
            service=service.slug,
            score=decision.score,
            incident_id=str(incident.id) if incident else None,
            caused_by=str(cause_id) if cause_id else None,
            **decision.features,
        )
