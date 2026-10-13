import base64
import binascii
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.auth.permissions import Permission, require
from opspilot_api.auth.principal import Principal
from opspilot_api.auth.tenancy import scoped
from opspilot_api.db.models import ActorType, AuditLog
from opspilot_api.db.session import get_session

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


def _encode_cursor(entry: AuditLog) -> str:
    raw = f"{entry.created_at.isoformat()}|{entry.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        created_at, entry_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(created_at), uuid.UUID(entry_id)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid cursor") from exc


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
            tuple_(AuditLog.created_at, AuditLog.id) < tuple_(*_decode_cursor(cursor))
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
        next_cursor=_encode_cursor(page[-1]) if more and page else None,
    )
