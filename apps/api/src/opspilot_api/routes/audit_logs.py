import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.auth.permissions import Permission, require
from opspilot_api.auth.principal import Principal
from opspilot_api.auth.tenancy import scoped
from opspilot_api.db.models import ActorType, AuditLog
from opspilot_api.db.session import get_session
from opspilot_api.pagination import decode_page_token, encode_page_token

router = APIRouter(prefix="/api/v1", tags=["audit"])


class AuditLogItem(BaseModel):
    id: uuid.UUID
    actor_type: ActorType
    actor_id: str
    action: str
    resource_type: str
    resource_id: str | None
    ip_address: str | None
    request_id: str | None
    metadata: dict[str, Any]
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogItem]
    next_cursor: str | None


@router.get("/audit-logs", response_model=AuditLogPage)
async def list_audit_logs(
    principal: Annotated[Principal, Depends(require(Permission.VIEW_AUDIT_LOGS))],
    session: Annotated[AsyncSession, Depends(get_session)],
    action: str | None = None,
    actor_id: str | None = None,
    resource_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    cursor: str | None = None,
) -> AuditLogPage:
    statement = scoped(select(AuditLog), AuditLog, principal)
    if action:
        statement = statement.where(AuditLog.action == action)
    if actor_id:
        statement = statement.where(AuditLog.actor_id == actor_id)
    if resource_type:
        statement = statement.where(AuditLog.resource_type == resource_type)
    if since:
        statement = statement.where(AuditLog.created_at >= since)
    if until:
        statement = statement.where(AuditLog.created_at < until)
    if cursor:
        statement = statement.where(
            tuple_(AuditLog.created_at, AuditLog.id) < tuple_(*decode_page_token(cursor))
        )
    statement = statement.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit + 1)

    entries = list((await session.execute(statement)).scalars())
    page, more = entries[:limit], len(entries) > limit
    return AuditLogPage(
        items=[
            AuditLogItem(
                id=e.id,
                actor_type=e.actor_type,
                actor_id=e.actor_id,
                action=e.action,
                resource_type=e.resource_type,
                resource_id=e.resource_id,
                ip_address=str(e.ip_address) if e.ip_address else None,
                request_id=e.request_id,
                metadata=e.metadata_json,
                created_at=e.created_at,
            )
            for e in page
        ],
        next_cursor=encode_page_token(page[-1].created_at, page[-1].id) if more and page else None,
    )
