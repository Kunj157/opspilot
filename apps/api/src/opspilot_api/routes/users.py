"""The organization's users and their roles, for administrators.

Read-only by design: Keycloak is the source of truth for users and roles.
A user row is created on first sign-in and its roles are replaced from the
token's realm roles on every sign-in, so what is shown here is the state as of
each user's latest sign-in. Grant, revoke, or disable access in Keycloak; there
are no endpoints to change roles here (see docs/architecture/user-management.md).
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.auth.permissions import Permission, permissions_for, require
from opspilot_api.auth.principal import Principal
from opspilot_api.auth.roles import Role
from opspilot_api.auth.tenancy import get_owned_or_404, scoped
from opspilot_api.db.models import User, UserStatus
from opspilot_api.db.session import get_session
from opspilot_api.pagination import decode_page_token, encode_page_token

router = APIRouter(prefix="/api/v1", tags=["users"])


class UserItem(BaseModel):
    id: uuid.UUID
    email: str | None
    display_name: str
    status: UserStatus
    roles: list[Role] = Field(description="Realm roles from the user's latest sign-in")
    permissions: list[Permission] = Field(description="What those roles allow in OpsPilot")
    created_at: datetime = Field(description="First sign-in")
    updated_at: datetime


class UserPage(BaseModel):
    items: list[UserItem]
    next_cursor: str | None


def _item(user: User) -> UserItem:
    roles = sorted(Role(r.name) for r in user.roles)
    return UserItem(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        status=user.status,
        roles=roles,
        permissions=sorted(permissions_for(roles)),
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.get("/users", response_model=UserPage)
async def list_users(
    principal: Annotated[Principal, Depends(require(Permission.MANAGE_USERS))],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> UserPage:
    """Users of the caller's organization, newest first. Read-only: roles come from Keycloak."""
    statement = scoped(select(User), User, principal)
    if cursor:
        statement = statement.where(
            tuple_(User.created_at, User.id) < tuple_(*decode_page_token(cursor))
        )
    statement = statement.order_by(User.created_at.desc(), User.id.desc()).limit(limit + 1)
    users = list(await session.scalars(statement))
    page, more = users[:limit], len(users) > limit
    return UserPage(
        items=[_item(u) for u in page],
        next_cursor=encode_page_token(page[-1].created_at, page[-1].id) if more and page else None,
    )


@router.get("/users/{user_id}", response_model=UserItem)
async def get_user(
    user_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require(Permission.MANAGE_USERS))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserItem:
    """One user of the caller's organization; another organization's user is 404."""
    return _item(await get_owned_or_404(session, User, user_id, principal))
