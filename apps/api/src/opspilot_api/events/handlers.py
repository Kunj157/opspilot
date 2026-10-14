"""What consumers do with events."""

import uuid

from prometheus_client import Counter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.agents.queue import enqueue
from opspilot_api.db.models import Incident, IncidentStatus, Investigation
from opspilot_api.events.consumer import Handler, PermanentError
from opspilot_api.events.envelope import Envelope

SHADOW_AGREEMENT = Counter(
    "opspilot_event_shadow_agreement_total",
    "Shadow consumer decisions compared with the direct call",
    ["agrees"],
)
REQUESTER = "event:incident.created.v1"


def investigation_requester(*, authoritative: bool) -> Handler:
    """incident.created.v1 → queue an investigation for detector incidents.

    In shadow mode it only checks that the direct call already did what the
    event would have done, and counts agreement; once authoritative it queues
    the investigation itself (enqueue is idempotent per incident).
    """

    async def handle(session: AsyncSession, envelope: Envelope) -> str:
        try:
            incident_id = uuid.UUID(str(envelope.payload["incident_id"]))
        except (KeyError, ValueError) as exc:
            raise PermanentError(f"no incident in payload: {exc}") from exc
        incident = await session.get(Incident, incident_id)
        if incident is None or incident.organization_id != envelope.organization_id:
            raise PermanentError(f"unknown incident {incident_id}")
        if incident.source != "detector":
            return "skipped: not a detector incident"
        if incident.status is IncidentStatus.RESOLVED:
            # Out of order: the incident ended before this event was handled.
            return "skipped: already resolved"
        if not authoritative:
            existing = await session.scalar(
                select(Investigation.id).where(Investigation.incident_id == incident.id).limit(1)
            )
            SHADOW_AGREEMENT.labels(str(existing is not None).lower()).inc()
            return "shadow: agrees" if existing else "shadow: direct call queued nothing"
        _, created = await enqueue(session, incident, REQUESTER)
        return "queued" if created else "already queued"

    return handle
