import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.auth.permissions import Permission, require
from opspilot_api.auth.principal import Principal
from opspilot_api.auth.tenancy import get_owned_or_404, scoped
from opspilot_api.db.base import OrganizationScoped
from opspilot_api.db.models import (
    ActorType,
    Incident,
    IncidentEvent,
    IncidentStatus,
    Service,
    Severity,
    User,
)
from opspilot_api.db.session import get_session
from opspilot_api.incidents import service as incidents
from opspilot_api.incidents.state_machine import ALLOWED_TRANSITIONS
from opspilot_api.pagination import decode_page_token, encode_page_token

router = APIRouter(prefix="/api/v1", tags=["incidents"])

Source = Literal["manual", "detector", "alertmanager"]


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    severity: Severity
    status: IncidentStatus
    source: str
    service_id: uuid.UUID | None
    started_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    detection_score: float | None
    assigned_user_id: uuid.UUID | None
    version: int
    created_at: datetime
    updated_at: datetime
    allowed_transitions: list[IncidentStatus]

    @classmethod
    def of(cls, incident: Incident) -> "IncidentOut":
        allowed = sorted(ALLOWED_TRANSITIONS[incident.status])
        return cls.model_validate({**_columns(incident), "allowed_transitions": allowed})


def _columns(incident: Incident) -> dict[str, Any]:
    return {c.key: getattr(incident, c.key) for c in Incident.__table__.columns}


class IncidentPage(BaseModel):
    items: list[IncidentOut]
    next_cursor: str | None


class IncidentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    severity: Severity
    service_id: uuid.UUID | None = None
    source: Source = "manual"


class VersionedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)


class IncidentUpdate(VersionedRequest):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    severity: Severity | None = None
    service_id: uuid.UUID | None = None
    assigned_user_id: uuid.UUID | None = None
    status: IncidentStatus | None = None

    @model_validator(mode="after")
    def status_alone(self) -> "IncidentUpdate":
        if self.status is not None and self.model_fields_set - {"version", "status"}:
            raise ValueError("change the status in a separate request from other fields")
        return self


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sequence: int
    event_type: str
    actor_type: ActorType
    actor_id: str
    title: str
    description: str | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")
    created_at: datetime


class EventList(BaseModel):
    items: list[EventOut]


def _conflict(code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, {"code": code, "message": message, **extra})


async def _apply(incident: Incident, change: Any) -> None:
    """Run a domain change and translate its errors into HTTP responses."""
    try:
        await change
    except incidents.IncidentConflictError as exc:
        raise _conflict(
            "stale_version",
            "The incident was changed by someone else. Reload and try again.",
            current_version=incident.version,
        ) from exc
    except incidents.InvalidTransitionError as exc:
        raise _conflict("invalid_transition", str(exc)) from exc


async def _require_owned(
    session: AsyncSession,
    model: type[OrganizationScoped],
    item_id: uuid.UUID | None,
    principal: Principal,
    field: str,
) -> None:
    if item_id is None:
        return
    item = await session.get(model, item_id)
    if item is None or item.organization_id != principal.organization_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            [
                {
                    "loc": ["body", field],
                    "msg": "not found in your organization",
                    "type": "value_error",
                }
            ],
        )


async def _finish(session: AsyncSession, incident: Incident) -> IncidentOut:
    await session.commit()
    await session.refresh(incident)
    return IncidentOut.of(incident)


@router.get("/incidents", response_model=IncidentPage)
async def list_incidents(
    principal: Annotated[Principal, Depends(require(Permission.VIEW_INCIDENTS))],
    session: Annotated[AsyncSession, Depends(get_session)],
    status_: Annotated[list[IncidentStatus] | None, Query(alias="status")] = None,
    severity: Annotated[list[Severity] | None, Query()] = None,
    service_id: uuid.UUID | None = None,
    assigned_user_id: uuid.UUID | None = None,
    source: Source | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> IncidentPage:
    statement = scoped(select(Incident), Incident, principal)
    if status_:
        statement = statement.where(Incident.status.in_(status_))
    if severity:
        statement = statement.where(Incident.severity.in_(severity))
    if service_id:
        statement = statement.where(Incident.service_id == service_id)
    if assigned_user_id:
        statement = statement.where(Incident.assigned_user_id == assigned_user_id)
    if source:
        statement = statement.where(Incident.source == source)
    if since:
        statement = statement.where(Incident.started_at >= since)
    if until:
        statement = statement.where(Incident.started_at < until)
    if cursor:
        statement = statement.where(
            tuple_(Incident.started_at, Incident.id) < tuple_(*decode_page_token(cursor))
        )
    statement = statement.order_by(Incident.started_at.desc(), Incident.id.desc()).limit(limit + 1)

    rows = list((await session.execute(statement)).scalars())
    page, more = rows[:limit], len(rows) > limit
    return IncidentPage(
        items=[IncidentOut.of(i) for i in page],
        next_cursor=encode_page_token(page[-1].started_at, page[-1].id) if more and page else None,
    )


@router.post("/incidents", response_model=IncidentOut, status_code=status.HTTP_201_CREATED)
async def create_incident(
    body: IncidentCreate,
    principal: Annotated[Principal, Depends(require(Permission.MANAGE_INCIDENTS))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IncidentOut:
    await _require_owned(session, Service, body.service_id, principal, "service_id")
    incident = await incidents.create_incident(
        session,
        incidents.Actor.from_principal(principal),
        title=body.title,
        description=body.description,
        severity=body.severity,
        service_id=body.service_id,
        source=body.source,
    )
    return await _finish(session, incident)


@router.get("/incidents/{incident_id}", response_model=IncidentOut)
async def get_incident(
    incident_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require(Permission.VIEW_INCIDENTS))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IncidentOut:
    return IncidentOut.of(await get_owned_or_404(session, Incident, incident_id, principal))


@router.patch("/incidents/{incident_id}", response_model=IncidentOut)
async def update_incident(
    incident_id: uuid.UUID,
    body: IncidentUpdate,
    principal: Annotated[Principal, Depends(require(Permission.MANAGE_INCIDENTS))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IncidentOut:
    incident = await get_owned_or_404(session, Incident, incident_id, principal)
    actor = incidents.Actor.from_principal(principal)
    if body.status is not None:
        await _apply(
            incident,
            incidents.transition(
                session, incident, body.status, expected_version=body.version, actor=actor
            ),
        )
    else:
        changes = body.model_dump(exclude_unset=True, exclude={"version", "status"})
        await _require_owned(session, Service, changes.get("service_id"), principal, "service_id")
        await _require_owned(
            session, User, changes.get("assigned_user_id"), principal, "assigned_user_id"
        )
        await _apply(
            incident,
            incidents.update_details(
                session, incident, expected_version=body.version, actor=actor, changes=changes
            ),
        )
    return await _finish(session, incident)


@router.post("/incidents/{incident_id}/acknowledge", response_model=IncidentOut)
async def acknowledge_incident(
    incident_id: uuid.UUID,
    body: VersionedRequest,
    principal: Annotated[Principal, Depends(require(Permission.MANAGE_INCIDENTS))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IncidentOut:
    incident = await get_owned_or_404(session, Incident, incident_id, principal)
    await _apply(
        incident,
        incidents.acknowledge(
            session,
            incident,
            expected_version=body.version,
            actor=incidents.Actor.from_principal(principal),
            assignee_id=incident.assigned_user_id or principal.user_id,
        ),
    )
    return await _finish(session, incident)


@router.post("/incidents/{incident_id}/investigate", response_model=IncidentOut)
async def investigate_incident(
    incident_id: uuid.UUID,
    body: VersionedRequest,
    principal: Annotated[Principal, Depends(require(Permission.START_INVESTIGATION))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IncidentOut:
    incident = await get_owned_or_404(session, Incident, incident_id, principal)
    await _apply(
        incident,
        incidents.transition(
            session,
            incident,
            IncidentStatus.INVESTIGATING,
            expected_version=body.version,
            actor=incidents.Actor.from_principal(principal),
        ),
    )
    return await _finish(session, incident)


@router.post("/incidents/{incident_id}/resolve", response_model=IncidentOut)
async def resolve_incident(
    incident_id: uuid.UUID,
    body: VersionedRequest,
    principal: Annotated[Principal, Depends(require(Permission.MANAGE_INCIDENTS))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IncidentOut:
    incident = await get_owned_or_404(session, Incident, incident_id, principal)
    await _apply(
        incident,
        incidents.transition(
            session,
            incident,
            IncidentStatus.RESOLVED,
            expected_version=body.version,
            actor=incidents.Actor.from_principal(principal),
        ),
    )
    return await _finish(session, incident)


@router.get("/incidents/{incident_id}/events", response_model=EventList)
async def list_incident_events(
    incident_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require(Permission.VIEW_INCIDENTS))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EventList:
    await get_owned_or_404(session, Incident, incident_id, principal)
    rows = await session.execute(
        select(IncidentEvent)
        .where(IncidentEvent.incident_id == incident_id)
        .order_by(IncidentEvent.sequence)
    )
    return EventList(items=[EventOut.model_validate(e) for e in rows.scalars()])
