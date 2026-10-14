"""Role → permission matrix and its enforcement."""

import enum
from collections.abc import Awaitable, Callable, Iterable
from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, status

from opspilot_api.auth.dependencies import get_principal
from opspilot_api.auth.principal import Principal
from opspilot_api.auth.roles import Role

logger = structlog.get_logger()


class Permission(enum.StrEnum):
    VIEW_SERVICES = "view_services"
    VIEW_INCIDENTS = "view_incidents"
    START_INVESTIGATION = "start_investigation"
    APPROVE_REMEDIATION = "approve_remediation"
    MANAGE_USERS = "manage_users"
    MANAGE_RUNBOOKS = "manage_runbooks"
    VIEW_AUDIT_LOGS = "view_audit_logs"
    MANAGE_SERVICES = "manage_services"
    MANAGE_INCIDENTS = "manage_incidents"
    MANAGE_MODELS = "manage_models"


_VIEWER = {Permission.VIEW_SERVICES, Permission.VIEW_INCIDENTS}
_OPERATOR = _VIEWER | {
    Permission.START_INVESTIGATION,
    Permission.MANAGE_RUNBOOKS,
    Permission.MANAGE_SERVICES,
    Permission.MANAGE_INCIDENTS,
}
_COMMANDER = _OPERATOR | {Permission.APPROVE_REMEDIATION, Permission.VIEW_AUDIT_LOGS}

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset(_VIEWER),
    Role.OPERATOR: frozenset(_OPERATOR),
    Role.INCIDENT_COMMANDER: frozenset(_COMMANDER),
    Role.ADMINISTRATOR: frozenset(Permission),
}


def permissions_for(roles: Iterable[Role]) -> frozenset[Permission]:
    granted: set[Permission] = set()
    for role in roles:
        granted |= ROLE_PERMISSIONS[role]
    return frozenset(granted)


def require(permission: Permission) -> Callable[..., Awaitable[Principal]]:
    """Dependency: the authenticated principal, or 403 if it lacks `permission`."""

    async def dependency(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if permission not in permissions_for(principal.roles):
            logger.warning("permission denied", permission=permission.value)
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
        return principal

    return dependency
