"""Service topology: every service in the organization and the calls between them."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.auth.permissions import Permission, require
from opspilot_api.auth.principal import Principal
from opspilot_api.auth.tenancy import scoped
from opspilot_api.db.models import (
    HealthStatus,
    Incident,
    IncidentStatus,
    Service,
    ServiceDependency,
)
from opspilot_api.db.session import get_session

router = APIRouter(prefix="/api/v1", tags=["topology"])


class TopologyNode(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    health_status: HealthStatus
    active_incidents: int
    investigating: bool


class TopologyEdge(BaseModel):
    source_id: uuid.UUID
    target_id: uuid.UUID


class Topology(BaseModel):
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]


@router.get("/topology", response_model=Topology)
async def get_topology(
    principal: Annotated[Principal, Depends(require(Permission.VIEW_SERVICES))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Topology:
    active = Incident.status != IncidentStatus.RESOLVED
    counts = (
        scoped(
            select(
                Incident.service_id,
                func.count().label("active"),
                func.bool_or(Incident.status == IncidentStatus.INVESTIGATING).label(
                    "investigating"
                ),
            ),
            Incident,
            principal,
        )
        .where(active)
        .group_by(Incident.service_id)
        .subquery()
    )
    nodes = await session.execute(
        scoped(
            select(Service, counts.c.active, counts.c.investigating),
            Service,
            principal,
        )
        .outerjoin(counts, counts.c.service_id == Service.id)
        .order_by(Service.name)
    )
    edges = await session.execute(
        select(ServiceDependency.source_service_id, ServiceDependency.target_service_id)
        .where(ServiceDependency.organization_id == principal.organization_id)
        .order_by(ServiceDependency.source_service_id, ServiceDependency.target_service_id)
    )
    return Topology(
        nodes=[
            TopologyNode(
                id=service.id,
                name=service.name,
                slug=service.slug,
                health_status=service.health_status,
                active_incidents=active_count or 0,
                investigating=bool(investigating),
            )
            for service, active_count, investigating in nodes
        ],
        edges=[TopologyEdge(source_id=s, target_id=t) for s, t in edges],
    )
