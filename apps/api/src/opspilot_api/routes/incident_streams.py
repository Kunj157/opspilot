"""Server-Sent Events: live incident updates (registered before /incidents/{id})."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.auth.permissions import Permission, require
from opspilot_api.auth.principal import Principal
from opspilot_api.auth.tenancy import get_owned_or_404
from opspilot_api.db.models import Incident, IncidentEvent
from opspilot_api.db.session import SessionFactory, get_session
from opspilot_api.events.broker import EventBroker
from opspilot_api.routes.incidents import EventOut, IncidentOut

router = APIRouter(prefix="/api/v1", tags=["incidents"])

BATCH = 200
STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _frame(event: IncidentEvent, incident: Incident) -> str:
    data = EventOut.model_validate(event).model_dump(mode="json")
    data["incident"] = IncidentOut.of(incident).model_dump(mode="json")
    return f"id: {event.sequence}\nevent: {event.event_type}\ndata: {json.dumps(data)}\n\n"


async def _events_after(
    factory: SessionFactory,
    principal: Principal,
    incident_id: uuid.UUID | None,
    after: int,
) -> list[tuple[IncidentEvent, Incident]]:
    async with factory() as session:
        statement = (
            select(IncidentEvent, Incident)
            .join(Incident, Incident.id == IncidentEvent.incident_id)
            .where(
                IncidentEvent.organization_id == principal.organization_id,
                IncidentEvent.sequence > after,
            )
            .order_by(IncidentEvent.sequence)
            .limit(BATCH)
        )
        if incident_id is not None:
            statement = statement.where(IncidentEvent.incident_id == incident_id)
        return [(row[0], row[1]) for row in (await session.execute(statement)).all()]


async def _latest_sequence(
    factory: SessionFactory, principal: Principal, incident_id: uuid.UUID | None
) -> int:
    async with factory() as session:
        statement = select(func.coalesce(func.max(IncidentEvent.sequence), 0)).where(
            IncidentEvent.organization_id == principal.organization_id
        )
        if incident_id is not None:
            statement = statement.where(IncidentEvent.incident_id == incident_id)
        return int((await session.execute(statement)).scalar_one())


def _parse_last_event_id(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


async def _stream(
    request: Request,
    principal: Principal,
    incident_id: uuid.UUID | None,
    last_event_id: int | None,
) -> AsyncIterator[str]:
    broker: EventBroker = request.app.state.event_broker
    factory: SessionFactory = request.app.state.session_factory
    heartbeat: float = request.app.state.settings.sse_heartbeat_seconds

    # Subscribe before reading the starting point so nothing can slip between.
    subscription = broker.subscribe(principal.organization_id, incident_id)
    try:
        after = (
            last_event_id
            if last_event_id is not None
            else await _latest_sequence(factory, principal, incident_id)
        )
        yield "retry: 3000\n: subscribed\n\n"
        while True:
            for event, incident in await _events_after(factory, principal, incident_id, after):
                yield _frame(event, incident)
                after = event.sequence
            try:
                await asyncio.wait_for(subscription.wake.wait(), timeout=heartbeat)
                subscription.wake.clear()
            except TimeoutError:
                yield ": heartbeat\n\n"
    finally:
        broker.unsubscribe(subscription)


@router.get("/incidents/stream", response_class=StreamingResponse)
async def stream_organization_incidents(
    request: Request,
    principal: Annotated[Principal, Depends(require(Permission.VIEW_INCIDENTS))],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    return StreamingResponse(
        _stream(request, principal, None, _parse_last_event_id(last_event_id)),
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )


@router.get("/incidents/{incident_id}/stream", response_class=StreamingResponse)
async def stream_incident(
    incident_id: uuid.UUID,
    request: Request,
    principal: Annotated[Principal, Depends(require(Permission.VIEW_INCIDENTS))],
    session: Annotated[AsyncSession, Depends(get_session)],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    await get_owned_or_404(session, Incident, incident_id, principal)
    return StreamingResponse(
        _stream(request, principal, incident_id, _parse_last_event_id(last_event_id)),
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )
