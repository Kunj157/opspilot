"""Write audit records. Callers commit them in the same transaction as the change."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.auth.principal import Principal
from opspilot_api.db.models import ActorType, AuditLog
from opspilot_api.redaction import redact
from opspilot_api.request_context import current_client_ip, current_request_id


async def record(
    session: AsyncSession,
    *,
    action: str,
    resource_type: str,
    principal: Principal | None = None,
    organization_id: uuid.UUID | None = None,
    actor_type: ActorType = ActorType.USER,
    actor_id: str | None = None,
    resource_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Add an audit record to the session.

    User actions pass `principal`; system actions pass `organization_id`,
    `actor_type`, and `actor_id` explicitly.
    """
    org = principal.organization_id if principal else organization_id
    actor = str(principal.user_id) if principal else actor_id
    if org is None or actor is None:
        raise ValueError("audit record needs an organization and an actor")
    session.add(
        AuditLog(
            organization_id=org,
            actor_type=actor_type,
            actor_id=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=current_client_ip.get(),
            request_id=current_request_id.get(),
            metadata_json=redact(metadata or {}),
        )
    )
