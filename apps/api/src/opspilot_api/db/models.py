"""Core identity and audit tables (DEVELOPMENT_PLAN.md §12.1)."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
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


class Severity(enum.StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IncidentStatus(enum.StrEnum):
    """States from DEVELOPMENT_PLAN.md §13; transitions live in incidents.state_machine."""

    DETECTED = "DETECTED"
    INVESTIGATING = "INVESTIGATING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    REMEDIATING = "REMEDIATING"
    VERIFYING = "VERIFYING"
    MONITORING = "MONITORING"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"


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


class ServiceDependency(UUIDPrimaryKey, OrganizationScoped, Base):
    """Directed edge: `source` calls `target`. Both services share the organization."""

    __tablename__ = "service_dependencies"
    __table_args__ = (
        UniqueConstraint("source_service_id", "target_service_id"),
        CheckConstraint("source_service_id <> target_service_id", name="no_self_dependency"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    source_service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE")
    )
    target_service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def _enum(cls: type[enum.StrEnum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class Incident(UUIDPrimaryKey, Timestamps, OrganizationScoped, Base):
    __tablename__ = "incidents"
    __table_args__ = (Index(None, "organization_id", "status", "started_at"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    service_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("services.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(5000))
    severity: Mapped[Severity] = mapped_column(_enum(Severity, "incident_severity"))
    status: Mapped[IncidentStatus] = mapped_column(
        _enum(IncidentStatus, "incident_status"), server_default=IncidentStatus.DETECTED.value
    )
    source: Mapped[str] = mapped_column(String(50))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detection_score: Mapped[float | None] = mapped_column(Float)
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    # Optimistic locking: every UPDATE checks and increments this.
    version: Mapped[int] = mapped_column(Integer, server_default="1")

    # SQLAlchemy reads this declarative attribute at class creation; never mutated.
    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class IncidentEvent(UUIDPrimaryKey, OrganizationScoped, Base):
    """Timeline entry. `sequence` orders events and resumes live streams."""

    __tablename__ = "incident_events"
    __table_args__ = (Index(None, "incident_id", "sequence"),)

    sequence: Mapped[int] = mapped_column(BigInteger, Identity(always=True), unique=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(100))
    actor_type: Mapped[ActorType] = mapped_column(_enum(ActorType, "actor_type"))
    actor_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(2000))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IdempotencyKey(Base):
    """Stored outcome of a create request, replayed when the same key is retried."""

    __tablename__ = "idempotency_keys"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(500))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
