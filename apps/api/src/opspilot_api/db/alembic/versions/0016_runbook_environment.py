"""runbook environment

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-14 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing runbooks had no environment, so they apply everywhere.
    op.add_column(
        "runbooks",
        sa.Column("environment", sa.String(length=32), server_default="all", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("runbooks", "environment")
