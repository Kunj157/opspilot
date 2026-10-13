"""incidents and timeline

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-13 17:04:47.864049
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=5000), nullable=True),
        sa.Column(
            "severity",
            sa.Enum("critical", "high", "medium", "low", name="incident_severity"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "DETECTED",
                "INVESTIGATING",
                "AWAITING_APPROVAL",
                "REMEDIATING",
                "VERIFYING",
                "MONITORING",
                "RESOLVED",
                "REJECTED",
                name="incident_status",
            ),
            server_default="DETECTED",
            nullable=False,
        ),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detection_score", sa.Float(), nullable=True),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["assigned_user_id"],
            ["users.id"],
            name=op.f("fk_incidents_assigned_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_incidents_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name=op.f("fk_incidents_service_id_services"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incidents")),
    )
    op.create_index(
        op.f("ix_incidents_organization_id_status_started_at"),
        "incidents",
        ["organization_id", "status", "started_at"],
        unique=False,
    )
    op.create_index(op.f("ix_incidents_service_id"), "incidents", ["service_id"], unique=False)
    op.create_table(
        "incident_events",
        sa.Column("sequence", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        # actor_type already exists (revision 0001).
        sa.Column(
            "actor_type", postgresql.ENUM(name="actor_type", create_type=False), nullable=False
        ),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_incident_events_incident_id_incidents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_incident_events_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incident_events")),
        sa.UniqueConstraint("sequence", name=op.f("uq_incident_events_sequence")),
    )
    op.create_index(
        op.f("ix_incident_events_incident_id_sequence"),
        "incident_events",
        ["incident_id", "sequence"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_incident_events_incident_id_sequence"), table_name="incident_events")
    op.drop_table("incident_events")
    op.drop_index(op.f("ix_incidents_service_id"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_organization_id_status_started_at"), table_name="incidents")
    op.drop_table("incidents")
    sa.Enum(name="incident_status").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="incident_severity").drop(op.get_bind(), checkfirst=False)
