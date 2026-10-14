"""Database models: identity, audit, service catalog, and incidents."""

import enum
import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
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
    Text,
    UniqueConstraint,
    func,
    text,
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
    """Incident lifecycle states; transitions live in incidents.state_machine."""

    DETECTED = "DETECTED"
    INVESTIGATING = "INVESTIGATING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    REMEDIATING = "REMEDIATING"
    VERIFYING = "VERIFYING"
    MONITORING = "MONITORING"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"


class RunbookStatus(enum.StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


# Dimensions of the runbook embedding model (bge-small-en-v1.5).
EMBEDDING_DIMENSIONS = 384


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
    __table_args__ = (
        Index(None, "organization_id", "status", "started_at"),
        Index(
            "uq_incidents_open_dedup_key",
            "organization_id",
            "dedup_key",
            unique=True,
            postgresql_where=text("dedup_key IS NOT NULL AND status <> 'RESOLVED'"),
        ),
    )

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
    # Detector incidents: organization + service + detector + failure category.
    # At most one unresolved incident per key (partial unique index).
    dedup_key: Mapped[str | None] = mapped_column(String(255))
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


class AnomalyDetection(UUIDPrimaryKey, OrganizationScoped, Base):
    """One detector decision about one service: what was measured and what it meant."""

    __tablename__ = "anomaly_detections"
    __table_args__ = (Index(None, "organization_id", "service_id", "created_at"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"))
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("incidents.id", ondelete="SET NULL"), index=True
    )
    detector: Mapped[str] = mapped_column(String(50))
    failure_category: Mapped[str] = mapped_column(String(50))
    outcome: Mapped[str] = mapped_column(String(20))
    score: Mapped[float | None] = mapped_column(Float)
    threshold: Mapped[float | None] = mapped_column(Float)
    features: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    model_version: Mapped[str | None] = mapped_column(String(50))
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DetectorCheckpoint(Base):
    """Rule state per service and detector, so a worker restart does not re-trigger."""

    __tablename__ = "detector_checkpoints"

    service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), primary_key=True
    )
    detector: Mapped[str] = mapped_column(String(50), primary_key=True)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Runbook(UUIDPrimaryKey, Timestamps, OrganizationScoped, Base):
    """A versioned operational procedure; `content` is the latest version's markdown."""

    __tablename__ = "runbooks"
    __table_args__ = (UniqueConstraint("organization_id", "slug"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    slug: Mapped[str] = mapped_column(String(63))
    title: Mapped[str] = mapped_column(String(200))
    # Slugs of the catalog services the runbook applies to (from its front matter).
    services: Mapped[list[str]] = mapped_column(JSONB, server_default="[]")
    owner: Mapped[str | None] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    source_url: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[RunbookStatus] = mapped_column(
        _enum(RunbookStatus, "runbook_status"), server_default=RunbookStatus.ACTIVE.value
    )


class RunbookChunk(UUIDPrimaryKey, Base):
    """One section of a runbook version with its embedding, for retrieval."""

    __tablename__ = "runbook_chunks"
    __table_args__ = (
        Index(
            "ix_runbook_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    runbook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("runbooks.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    ordinal: Mapped[int] = mapped_column(Integer)
    heading: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    # Text that reads like instructions to a model (prompt injection), kept but marked.
    flagged: Mapped[bool] = mapped_column(server_default=text("false"))


class InvestigationStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    # Stopped early (limits or model failure): evidence kept, manual review advised.
    PARTIAL = "partial"
    FAILED = "failed"


class RemediationAction(enum.StrEnum):
    ROLLBACK_DEPLOYMENT = "ROLLBACK_DEPLOYMENT"
    RESTART_DEPLOYMENT = "RESTART_DEPLOYMENT"
    SCALE_DEPLOYMENT = "SCALE_DEPLOYMENT"
    PAUSE_ROLLOUT = "PAUSE_ROLLOUT"
    NO_ACTION = "NO_ACTION"


class ProposalStatus(enum.StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"


class Investigation(UUIDPrimaryKey, Timestamps, OrganizationScoped, Base):
    """One agent investigation of an incident; the row is also its job in the queue."""

    __tablename__ = "investigations"
    __table_args__ = (
        Index(
            "uq_investigations_active_incident",
            "incident_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
        Index(None, "status", "lease_until"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[InvestigationStatus] = mapped_column(
        _enum(InvestigationStatus, "investigation_status"),
        server_default=InvestigationStatus.QUEUED.value,
    )
    requested_by: Mapped[str] = mapped_column(String(255))
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_node: Mapped[str | None] = mapped_column(String(50))
    round: Mapped[int] = mapped_column(Integer, server_default="0")
    # Graph state persisted after every node, so a restarted worker resumes.
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    # Final or partial outcome: summary, hypotheses, unknowns.
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(String(500))
    tool_calls: Mapped[int] = mapped_column(Integer, server_default="0")
    input_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    cost_usd: Mapped[float] = mapped_column(Float, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentRun(UUIDPrimaryKey, OrganizationScoped, Base):
    __tablename__ = "agent_runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    agent_name: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20))
    model_provider: Mapped[str] = mapped_column(String(50))
    model_name: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(20))
    input_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    estimated_cost: Mapped[float] = mapped_column(Float, server_default="0")
    latency_ms: Mapped[float] = mapped_column(Float, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(100))
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentToolCall(UUIDPrimaryKey, OrganizationScoped, Base):
    __tablename__ = "agent_tool_calls"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    tool_name: Mapped[str] = mapped_column(String(100))
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20))
    result_summary: Mapped[str | None] = mapped_column(String(2000))
    error: Mapped[str | None] = mapped_column(String(500))
    duration_ms: Mapped[float] = mapped_column(Float, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Evidence(UUIDPrimaryKey, OrganizationScoped, Base):
    """A cited observation: what was queried, over which time range, and what it showed."""

    __tablename__ = "evidence"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("investigations.id", ondelete="SET NULL")
    )
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    evidence_type: Mapped[str] = mapped_column(String(50))
    source: Mapped[str] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(String(2000))
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    query: Mapped[str | None] = mapped_column(String(2000))
    time_range_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_range_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RemediationProposal(UUIDPrimaryKey, Timestamps, OrganizationScoped, Base):
    """An allow-listed action proposed by an agent; nothing runs without approval (phase 9)."""

    __tablename__ = "remediation_proposals"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("investigations.id", ondelete="SET NULL")
    )
    runbook_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("runbooks.id", ondelete="SET NULL")
    )
    action_type: Mapped[RemediationAction] = mapped_column(
        _enum(RemediationAction, "remediation_action")
    )
    description: Mapped[str] = mapped_column(String(2000))
    # Target and bounded settings, e.g. {"namespace": "demo", "deployment": "checkout"}.
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB)
    risk_level: Mapped[str] = mapped_column(String(20))
    status: Mapped[ProposalStatus] = mapped_column(
        _enum(ProposalStatus, "proposal_status"), server_default=ProposalStatus.PENDING.value
    )
    verification_plan: Mapped[dict[str, Any]] = mapped_column(JSONB)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, server_default="[]")
    created_by_agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Bumped on any change; an approval must name the version it reviewed.
    version: Mapped[int] = mapped_column(Integer, server_default="1")


class Postmortem(UUIDPrimaryKey, Timestamps, OrganizationScoped, Base):
    """A drafted postmortem for a resolved incident; regenerated on request."""

    __tablename__ = "postmortems"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), unique=True
    )
    # pending → ready (or ready with a template when the model failed).
    status: Mapped[str] = mapped_column(String(20), server_default="pending")
    content: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    generated_by: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(20))


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
