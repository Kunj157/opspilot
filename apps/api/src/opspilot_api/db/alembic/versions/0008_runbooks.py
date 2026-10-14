"""runbooks and embedded runbook chunks (pgvector)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-14 03:00:00.000000
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "runbooks",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "services",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("owner", sa.String(length=100), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "archived", name="runbook_status"),
            server_default="active",
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
            name=op.f("fk_runbooks_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runbooks")),
        sa.UniqueConstraint(
            "organization_id", "slug", name=op.f("uq_runbooks_organization_id_slug")
        ),
    )
    op.create_table(
        "runbook_chunks",
        sa.Column("runbook_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("heading", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(dim=384), nullable=False),
        sa.Column("flagged", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_runbook_chunks_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["runbook_id"],
            ["runbooks.id"],
            name=op.f("fk_runbook_chunks_runbook_id_runbooks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runbook_chunks")),
    )
    op.create_index(
        "ix_runbook_chunks_embedding",
        "runbook_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        op.f("ix_runbook_chunks_organization_id"), "runbook_chunks", ["organization_id"]
    )
    op.create_index(op.f("ix_runbook_chunks_runbook_id"), "runbook_chunks", ["runbook_id"])


def downgrade() -> None:
    op.drop_table("runbook_chunks")
    op.drop_table("runbooks")
    sa.Enum(name="runbook_status").drop(op.get_bind(), checkfirst=False)
    # The vector extension stays installed; dropping it needs superuser rights.
