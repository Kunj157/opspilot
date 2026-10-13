"""Core identity and audit tables (DEVELOPMENT_PLAN.md §12.1)."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Table,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opspilot_api.db.base import Base, OrganizationScoped, Timestamps, UUIDPrimaryKey


class UserStatus(enum.StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class HealthStatus(enum.StrEnum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"


class ActorType(enum.StrEnum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class Organization(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(63), unique=True)


user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)


class User(UUIDPrimaryKey, Timestamps, OrganizationScoped, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("issuer", "external_auth_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    # A token subject is only unique within its issuer.
    issuer: Mapped[str] = mapped_column(String(255))
    external_auth_id: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status", values_callable=lambda e: [m.value for m in e]),
        server_default=UserStatus.ACTIVE.value,
    )

    roles: Mapped[list[Role]] = relationship(secondary=user_roles, lazy="selectin")


class AuditLog(UUIDPrimaryKey, OrganizationScoped, Base):
    """Append-only: a database trigger rejects UPDATE and DELETE."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index(None, "organization_id", "created_at"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    actor_type: Mapped[ActorType] = mapped_column(
        Enum(ActorType, name="actor_type", values_callable=lambda e: [m.value for m in e])
    )
    actor_id: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(INET)
    request_id: Mapped[str | None] = mapped_column(String(128))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Service(UUIDPrimaryKey, Timestamps, OrganizationScoped, Base):
    __tablename__ = "services"
    __table_args__ = (UniqueConstraint("organization_id", "slug"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(63))
    description: Mapped[str | None] = mapped_column(String(2000))
    owner_team: Mapped[str | None] = mapped_column(String(100))
    repository_url: Mapped[str | None] = mapped_column(String(500))
    namespace: Mapped[str | None] = mapped_column(String(63))
    deployment_name: Mapped[str | None] = mapped_column(String(253))
    health_status: Mapped[HealthStatus] = mapped_column(
        Enum(HealthStatus, name="health_status", values_callable=lambda e: [m.value for m in e]),
        server_default=HealthStatus.UNKNOWN.value,
    )
