"""The only code path that changes incidents.

Every change checks the caller's expected version (optimistic locking),
writes a timeline event and an audit record in the same transaction, and
leaves committing to the caller.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from opspilot_api.audit.service import record
from opspilot_api.auth.principal import Principal
from opspilot_api.db.models import ActorType, Incident, IncidentEvent, IncidentStatus, Severity
from opspilot_api.incidents.state_machine import can_transition


class InvalidTransitionError(Exception):
    """The requested change is not allowed from the incident's current state."""


class IncidentConflictError(Exception):
    """The incident changed since the caller last read it."""


@dataclass(frozen=True)
class Actor:
    type: ActorType
    id: str
    organization_id: uuid.UUID

    @classmethod
    def from_principal(cls, principal: Principal) -> "Actor":
        return cls(ActorType.USER, str(principal.user_id), principal.organization_id)


DETAIL_FIELDS = frozenset({"title", "description", "severity", "service_id", "assigned_user_id"})


async def _write_trails(
    session: AsyncSession,
    incident: Incident,
    actor: Actor,
    *,
    event_type: str,
    title: str,
    metadata: dict[str, Any],
) -> IncidentEvent:
    event = IncidentEvent(
        organization_id=incident.organization_id,
        incident_id=incident.id,
        event_type=event_type,
        actor_type=actor.type,
        actor_id=actor.id,
        title=title,
        metadata_json=metadata,
    )
    session.add(event)
    await record(
        session,
        organization_id=actor.organization_id,
        actor_type=actor.type,
        actor_id=actor.id,
        action=event_type,
        resource_type="incident",
        resource_id=str(incident.id),
        metadata=metadata,
    )
    return event


async def _flush(session: AsyncSession) -> None:
    try:
        await session.flush()
    except StaleDataError as exc:
        raise IncidentConflictError("incident was changed concurrently") from exc


def _label(status: IncidentStatus) -> str:
    return status.value.replace("_", " ").title()


def _check_version(incident: Incident, expected_version: int) -> None:
    if incident.version != expected_version:
        raise IncidentConflictError(
            f"expected version {expected_version}, current is {incident.version}"
        )


async def create_incident(
    session: AsyncSession,
    actor: Actor,
    *,
    title: str,
    severity: Severity,
    source: str,
    description: str | None = None,
    service_id: uuid.UUID | None = None,
    detection_score: float | None = None,
    dedup_key: str | None = None,
) -> Incident:
    incident = Incident(
        organization_id=actor.organization_id,
        title=title,
        description=description,
        severity=severity,
        source=source,
        service_id=service_id,
        detection_score=detection_score,
        dedup_key=dedup_key,
        status=IncidentStatus.DETECTED,
    )
    session.add(incident)
    await session.flush()
    await _write_trails(
        session,
        incident,
        actor,
        event_type="incident.created",
        title="Incident detected",
        metadata={"severity": severity.value, "source": source},
    )
    await session.flush()
    return incident


async def note(
    session: AsyncSession,
    incident: Incident,
    actor: Actor,
    *,
    event_type: str,
    title: str,
    metadata: dict[str, Any],
) -> IncidentEvent:
    """A timeline event that does not change the incident itself (no version bump)."""
    event = await _write_trails(
        session, incident, actor, event_type=event_type, title=title, metadata=metadata
    )
    await session.flush()
    return event


async def transition(
    session: AsyncSession,
    incident: Incident,
    target: IncidentStatus,
    *,
    expected_version: int,
    actor: Actor,
    reason: str | None = None,
) -> IncidentEvent:
    _check_version(incident, expected_version)
    source = incident.status
    if not can_transition(source, target):
        raise InvalidTransitionError(f"{source.value} → {target.value} is not allowed")

    incident.status = target
    if target is IncidentStatus.RESOLVED:
        incident.resolved_at = datetime.now(UTC)
    metadata: dict[str, Any] = {"from": source.value, "to": target.value}
    if reason:
        metadata["reason"] = reason
    event = await _write_trails(
        session,
        incident,
        actor,
        event_type="incident.status_changed",
        title=f"{_label(source)} → {_label(target)}",
        metadata=metadata,
    )
    await _flush(session)
    return event


async def acknowledge(
    session: AsyncSession,
    incident: Incident,
    *,
    expected_version: int,
    actor: Actor,
    assignee_id: uuid.UUID | None,
) -> IncidentEvent:
    _check_version(incident, expected_version)
    if incident.acknowledged_at is not None:
        raise InvalidTransitionError("incident is already acknowledged")
    if incident.status is IncidentStatus.RESOLVED:
        raise InvalidTransitionError("a resolved incident cannot be acknowledged")

    incident.acknowledged_at = datetime.now(UTC)
    if assignee_id is not None:
        incident.assigned_user_id = assignee_id
    event = await _write_trails(
        session,
        incident,
        actor,
        event_type="incident.acknowledged",
        title="Acknowledged",
        metadata={
            "assigned_user_id": str(incident.assigned_user_id)
            if incident.assigned_user_id
            else None
        },
    )
    await _flush(session)
    return event


async def update_details(
    session: AsyncSession,
    incident: Incident,
    *,
    expected_version: int,
    actor: Actor,
    changes: dict[str, Any],
) -> IncidentEvent:
    _check_version(incident, expected_version)
    unknown = set(changes) - DETAIL_FIELDS
    if unknown:
        raise ValueError(f"not editable: {sorted(unknown)}")
    if incident.status is IncidentStatus.RESOLVED:
        raise InvalidTransitionError("a resolved incident cannot be edited")

    for field, value in changes.items():
        setattr(incident, field, value)
    event = await _write_trails(
        session,
        incident,
        actor,
        event_type="incident.updated",
        title="Details updated",
        metadata={"changed": sorted(changes)},
    )
    await _flush(session)
    return event
