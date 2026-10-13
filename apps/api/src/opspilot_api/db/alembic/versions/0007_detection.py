"""detection records, detector checkpoints, incident deduplication

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-14 02:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("incidents", sa.Column("dedup_key", sa.String(length=255), nullable=True))
    op.create_index(
        "uq_incidents_open_dedup_key",
        "incidents",
        ["organization_id", "dedup_key"],
        unique=True,
        postgresql_where=sa.text("dedup_key IS NOT NULL AND status <> 'RESOLVED'"),
    )
    op.create_table(
        "anomaly_detections",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=True),
        sa.Column("detector", sa.String(length=50), nullable=False),
        sa.Column("failure_category", sa.String(length=50), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column(
            "features",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("model_version", sa.String(length=50), nullable=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
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
            name=op.f("fk_anomaly_detections_incident_id_incidents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_anomaly_detections_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name=op.f("fk_anomaly_detections_service_id_services"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_anomaly_detections")),
    )
    op.create_index(
        op.f("ix_anomaly_detections_incident_id"), "anomaly_detections", ["incident_id"]
    )
    op.create_index(
        op.f("ix_anomaly_detections_organization_id_service_id_created_at"),
        "anomaly_detections",
        ["organization_id", "service_id", "created_at"],
    )
    op.create_table(
        "detector_checkpoints",
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("detector", sa.String(length=50), nullable=False),
        sa.Column("state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name=op.f("fk_detector_checkpoints_service_id_services"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("service_id", "detector", name=op.f("pk_detector_checkpoints")),
    )


def downgrade() -> None:
    op.drop_table("detector_checkpoints")
    op.drop_table("anomaly_detections")
    op.drop_index("uq_incidents_open_dedup_key", table_name="incidents")
    op.drop_column("incidents", "dedup_key")
