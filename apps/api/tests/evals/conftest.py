from collections.abc import Iterator

import pytest
from alembic import command
from testcontainers.community.postgres import PostgresContainer

from opspilot_api.db.migrations import alembic_config


@pytest.fixture(scope="session")
def migrated_database_url() -> Iterator[str]:
    with PostgresContainer("pgvector/pgvector:0.8.0-pg17", driver="psycopg") as container:
        url = container.get_connection_url()
        command.upgrade(alembic_config(url), "head")
        yield url
