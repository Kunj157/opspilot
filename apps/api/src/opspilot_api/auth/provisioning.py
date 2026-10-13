"""Create or update the organization and user behind a verified token.

All writes are idempotent upserts, so concurrent first requests from the same
user cannot create duplicates.
"""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.auth.principal import Principal
from opspilot_api.auth.roles import Role
from opspilot_api.auth.tokens import TokenIdentity
from opspilot_api.db.models import Organization, User, UserStatus, user_roles
from opspilot_api.db.models import Role as RoleRow


class AccessDeniedError(Exception):
    """Authenticated, but this identity may not use OpsPilot. Message is for logs only."""


async def _organization_id(session: AsyncSession, slug: str) -> uuid.UUID:
    await session.execute(
        insert(Organization)
        .values(name=slug, slug=slug)
        .on_conflict_do_nothing(index_elements=[Organization.slug])
    )
    org_id: uuid.UUID = (
        await session.execute(select(Organization.id).where(Organization.slug == slug))
    ).scalar_one()
    return org_id


async def _sync_roles(session: AsyncSession, user_id: uuid.UUID, roles: frozenset[str]) -> None:
    wanted = (
        (await session.execute(select(RoleRow.id).where(RoleRow.name.in_(roles)))).scalars().all()
    )
    await session.execute(
        delete(user_roles).where(
            user_roles.c.user_id == user_id, user_roles.c.role_id.not_in(wanted)
        )
    )
    if wanted:
        await session.execute(
            insert(user_roles)
            .values([{"user_id": user_id, "role_id": role_id} for role_id in wanted])
            .on_conflict_do_nothing()
        )


async def provision(session: AsyncSession, identity: TokenIdentity) -> Principal:
    organization_id = await _organization_id(session, identity.organization)

    await session.execute(
        insert(User)
        .values(
            organization_id=organization_id,
            issuer=identity.issuer,
            external_auth_id=identity.subject,
            email=identity.email,
            display_name=identity.display_name,
        )
        .on_conflict_do_nothing(index_elements=[User.issuer, User.external_auth_id])
    )
    user = (
        await session.execute(
            select(User).where(
                User.issuer == identity.issuer, User.external_auth_id == identity.subject
            )
        )
    ).scalar_one()

    if user.organization_id != organization_id:
        await session.rollback()
        raise AccessDeniedError("token organization differs from the user's organization")
    if user.status is UserStatus.DISABLED:
        await session.rollback()
        raise AccessDeniedError("user is disabled")

    user.email = identity.email
    user.display_name = identity.display_name
    await _sync_roles(session, user.id, identity.roles)
    await session.commit()

    return Principal(
        user_id=user.id,
        organization_id=organization_id,
        organization_slug=identity.organization,
        subject=identity.subject,
        email=identity.email,
        display_name=identity.display_name,
        roles=frozenset(Role(name) for name in identity.roles),
    )
