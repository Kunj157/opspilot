"""notify listeners when incident events are committed

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-13 18:30:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NOTIFY is delivered only when the inserting transaction commits, so
    # listeners never hear about rolled-back changes.
    op.execute(
        """
        CREATE FUNCTION notify_incident_event() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            PERFORM pg_notify(
                'incident_events',
                json_build_object(
                    'sequence', NEW.sequence,
                    'organization_id', NEW.organization_id,
                    'incident_id', NEW.incident_id
                )::text
            );
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER incident_events_notify AFTER INSERT ON incident_events"
        " FOR EACH ROW EXECUTE FUNCTION notify_incident_event()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER incident_events_notify ON incident_events")
    op.execute("DROP FUNCTION notify_incident_event()")
