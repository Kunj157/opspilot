"""Turns detector decisions into incidents, timeline events, and service health.

Deduplication: at most one unresolved incident per organization, service,
detector, and failure category, enforced by a partial unique index, so even
concurrent workers cannot open two.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.db.models import (
    ActorType,
    AnomalyDetection,
    HealthStatus,
    Incident,
    IncidentStatus,
    Service,
    Severity,
)
from opspilot_api.detection.rules import Decision, ErrorRateRule, Outcome
from opspilot_api.incidents.service import Actor, create_incident, note

MODEL_VERSION = "rule-v1"


def dedup_key(service: Service, rule: ErrorRateRule) -> str:
    return f"{service.id}:{rule.name}:{rule.failure_category}"


def _severity(score: float) -> Severity:
    if score >= 6:
        return Severity.CRITICAL
    if score >= 2:
        return Severity.HIGH
    return Severity.MEDIUM


async def _open_incident(session: AsyncSession, service: Service, key: str) -> Incident | None:
    result: Incident | None = await session.scalar(
        select(Incident).where(
            Incident.organization_id == service.organization_id,
            Incident.dedup_key == key,
            Incident.status != IncidentStatus.RESOLVED,
        )
    )
    return result


async def _open_or_create(
    session: AsyncSession, service: Service, rule: ErrorRateRule, decision: Decision, actor: Actor
) -> Incident:
    key = dedup_key(service, rule)
    if existing := await _open_incident(session, service, key):
        return existing
    score = decision.score or 0.0
    rate = decision.features.get("error_rate", 0.0)
    try:
        async with session.begin_nested():
            incident = await create_incident(
                session,
                actor,
                title=f"High error rate on {service.name}",
                description=(
                    f"{rate:.1%} of requests to {service.name} are failing "
                    f"(threshold {decision.threshold:.0%}), sustained for "
                    f"{rule.trigger_windows} evaluation windows."
                ),
                severity=_severity(score),
                source="detector",
                service_id=service.id,
                detection_score=score,
                dedup_key=key,
            )
    except IntegrityError:
        # Another worker opened it first; use theirs.
        found = await _open_incident(session, service, key)
        if found is None:
            raise
        return found
    return incident


def _record(
    session: AsyncSession,
    service: Service,
    rule: ErrorRateRule,
    decision: Decision,
    incident: Incident | None,
    window_start: datetime,
    window_end: datetime,
) -> None:
    session.add(
        AnomalyDetection(
            organization_id=service.organization_id,
            service_id=service.id,
            incident_id=incident.id if incident else None,
            detector=rule.name,
            failure_category=rule.failure_category,
            outcome=decision.outcome.value,
            score=decision.score,
            threshold=decision.threshold,
            features=decision.features,
            model_version=MODEL_VERSION,
            window_start=window_start,
            window_end=window_end,
        )
    )


async def apply_impact(
    session: AsyncSession,
    service: Service,
    rule: ErrorRateRule,
    decision: Decision,
    *,
    cause: Service,
    window_start: datetime,
    window_end: datetime,
) -> Incident | None:
    """A caller failing because a service it depends on fails.

    The cause's incident gets an impact note instead of a second incident;
    without an open incident on the cause, this falls back to apply_decision.
    """
    if decision.outcome is Outcome.NONE:
        return None
    incident = await _open_incident(session, cause, dedup_key(cause, rule))
    if incident is None:
        return await apply_decision(
            session, service, rule, decision, window_start=window_start, window_end=window_end
        )
    if decision.outcome is Outcome.TRIGGERED:
        actor = Actor(ActorType.SYSTEM, f"detector:{rule.name}", service.organization_id)
        await note(
            session,
            incident,
            actor,
            event_type="incident.impact_detected",
            title=f"{service.name} is also affected",
            metadata={"service_id": str(service.id), "detector": rule.name, **decision.features},
        )
    service.health_status = (
        HealthStatus.HEALTHY if decision.outcome is Outcome.RECOVERED else HealthStatus.DEGRADED
    )
    _record(session, service, rule, decision, incident, window_start, window_end)
    await session.flush()
    return incident


async def apply_decision(
    session: AsyncSession,
    service: Service,
    rule: ErrorRateRule,
    decision: Decision,
    *,
    window_start: datetime,
    window_end: datetime,
) -> Incident | None:
    """Apply one decision for one service; the caller commits."""
    if decision.outcome is Outcome.NONE:
        return None
    actor = Actor(ActorType.SYSTEM, f"detector:{rule.name}", service.organization_id)
    incident: Incident | None
    if decision.outcome in {Outcome.TRIGGERED, Outcome.ONGOING}:
        incident = await _open_or_create(session, service, rule, decision, actor)
        score = decision.score or 0.0
        if decision.outcome is Outcome.TRIGGERED:
            # Published as telemetry.anomaly.detected.v1: identifiers and numbers only.
            await note(
                session,
                incident,
                actor,
                event_type="incident.anomaly_detected",
                title=f"Anomaly detected on {service.name} ({rule.failure_category})",
                metadata={
                    "service_id": str(service.id),
                    "detector": rule.name,
                    "failure_category": rule.failure_category,
                    "score": decision.score,
                    "threshold": decision.threshold,
                },
            )
        service.health_status = HealthStatus.CRITICAL if score >= 6 else HealthStatus.DEGRADED
    else:
        incident = await _open_incident(session, service, dedup_key(service, rule))
        service.health_status = HealthStatus.HEALTHY
        if incident is not None:
            await note(
                session,
                incident,
                actor,
                event_type="incident.signal_recovered",
                title="Error rate back to normal",
                metadata={"detector": rule.name, **decision.features},
            )
    _record(session, service, rule, decision, incident, window_start, window_end)
    await session.flush()
    return incident
