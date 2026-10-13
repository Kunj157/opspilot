"""service catalog

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-13 16:58:06.082581
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "services",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("owner_team", sa.String(length=100), nullable=True),
        sa.Column("repository_url", sa.String(length=500), nullable=True),
        sa.Column("namespace", sa.String(length=63), nullable=True),
        sa.Column("deployment_name", sa.String(length=253), nullable=True),
        sa.Column(
            "health_status",
            sa.Enum("unknown", "healthy", "degraded", "critical", name="health_status"),
            server_default="unknown",
            nullable=False,
        ),
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
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_services_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_services")),
        sa.UniqueConstraint(
            "organization_id", "slug", name=op.f("uq_services_organization_id_slug")
        ),
    )


def downgrade() -> None:
    op.drop_table("services")
    sa.Enum(name="health_status").drop(op.get_bind(), checkfirst=False)
