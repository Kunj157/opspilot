"""identity and audit tables

Revision ID: 0001
Revises:
Create Date: 2026-10-13 15:09:43.082820
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = ["viewer", "operator", "incident-commander", "administrator"]

actor_type = postgresql.ENUM("user", "agent", "system", name="actor_type", create_type=False)
user_status = postgresql.ENUM("active", "disabled", name="user_status", create_type=False)


def upgrade() -> None:
    actor_type.create(op.get_bind())
    user_status.create(op.get_bind())

    op.create_table(
        "organizations",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=63), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
        sa.UniqueConstraint("slug", name=op.f("uq_organizations_slug")),
    )
    roles = op.create_table(
        "roles",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("name", name=op.f("uq_roles_name")),
    )
    op.bulk_insert(roles, [{"id": i, "name": name} for i, name in enumerate(ROLES, start=1)])

    op.create_table(
        "audit_logs",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("actor_type", actor_type, nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
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
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_audit_logs_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(
        op.f("ix_audit_logs_organization_id_created_at"),
        "audit_logs",
        ["organization_id", "created_at"],
    )
    # Audit records are append-only: reject UPDATE and DELETE at the database.
    op.execute(
        """
        CREATE FUNCTION audit_logs_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only (% rejected)', TG_OP;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER audit_logs_append_only BEFORE UPDATE OR DELETE ON audit_logs"
        " FOR EACH ROW EXECUTE FUNCTION audit_logs_append_only()"
    )

    op.create_table(
        "users",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("issuer", sa.String(length=255), nullable=False),
        sa.Column("external_auth_id", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("status", user_status, server_default="active", nullable=False),
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
            name=op.f("fk_users_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint(
            "issuer", "external_auth_id", name=op.f("uq_users_issuer_external_auth_id")
        ),
    )
    op.create_index(op.f("ix_users_organization_id"), "users", ["organization_id"])
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], name=op.f("fk_user_roles_role_id_roles"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_roles_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "role_id", name=op.f("pk_user_roles")),
    )


def downgrade() -> None:
    op.drop_table("user_roles")
    op.drop_index(op.f("ix_users_organization_id"), table_name="users")
    op.drop_table("users")
    op.execute("DROP TRIGGER audit_logs_append_only ON audit_logs")
    op.execute("DROP FUNCTION audit_logs_append_only()")
    op.drop_index(op.f("ix_audit_logs_organization_id_created_at"), table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_table("roles")
    op.drop_table("organizations")
    user_status.drop(op.get_bind())
    actor_type.drop(op.get_bind())
