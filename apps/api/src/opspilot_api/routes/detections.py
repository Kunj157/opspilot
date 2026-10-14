"""Detector decisions behind an incident: the evidence for why it was opened."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.auth.permissions import Permission, require
from opspilot_api.auth.principal import Principal
from opspilot_api.auth.tenancy import get_owned_or_404
from opspilot_api.db.models import AnomalyDetection, Incident
from opspilot_api.db.session import get_session

router = APIRouter(prefix="/api/v1", tags=["incidents"])

MAX_DETECTIONS = 100


class DetectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    # The incident's own service, or a caller affected by it.
    service_id: uuid.UUID
    detector: str
    failure_category: str
    outcome: str
    score: float | None
    threshold: float | None
    features: dict[str, Any]
    model_version: str | None
    window_start: datetime
    window_end: datetime
    created_at: datetime


class DetectionList(BaseModel):
    items: list[DetectionOut]


@router.get("/incidents/{incident_id}/detections", response_model=DetectionList)
async def list_detections(
    incident_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require(Permission.VIEW_INCIDENTS))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DetectionList:
    await get_owned_or_404(session, Incident, incident_id, principal)
    rows = await session.scalars(
        select(AnomalyDetection)
        .where(AnomalyDetection.incident_id == incident_id)
        .order_by(AnomalyDetection.created_at.desc(), AnomalyDetection.id)
        .limit(MAX_DETECTIONS)
    )
    return DetectionList(items=[DetectionOut.model_validate(r) for r in rows])
