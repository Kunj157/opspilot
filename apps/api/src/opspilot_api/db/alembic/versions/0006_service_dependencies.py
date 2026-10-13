"""service dependencies

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-13 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "service_dependencies",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("source_service_id", sa.Uuid(), nullable=False),
        sa.Column("target_service_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "source_service_id <> target_service_id",
            name=op.f("ck_service_dependencies_no_self_dependency"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_service_dependencies_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_service_id"],
            ["services.id"],
            name=op.f("fk_service_dependencies_source_service_id_services"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_service_id"],
            ["services.id"],
            name=op.f("fk_service_dependencies_target_service_id_services"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_service_dependencies")),
        sa.UniqueConstraint(
            "source_service_id",
            "target_service_id",
            name=op.f("uq_service_dependencies_source_service_id_target_service_id"),
        ),
    )
    op.create_index(
        op.f("ix_service_dependencies_organization_id"),
        "service_dependencies",
        ["organization_id"],
    )
    op.create_index(
        op.f("ix_service_dependencies_target_service_id"),
        "service_dependencies",
        ["target_service_id"],
    )


def downgrade() -> None:
    op.drop_table("service_dependencies")
