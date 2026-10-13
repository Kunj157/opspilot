"""Organization isolation for reads and writes.

A resource in another organization is reported exactly like a missing one,
so callers cannot probe for IDs that exist elsewhere.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.auth.principal import Principal
from opspilot_api.db.base import OrganizationScoped


async def get_owned_or_404[T: OrganizationScoped](
    session: AsyncSession, model: type[T], resource_id: uuid.UUID, principal: Principal
) -> T:
    resource = await session.get(model, resource_id)
    if resource is None or resource.organization_id != principal.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    return resource
