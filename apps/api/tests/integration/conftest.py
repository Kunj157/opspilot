from collections.abc import AsyncIterator, Iterator

import pytest
from alembic import command
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.kafka import RedpandaContainer
from testcontainers.community.postgres import PostgresContainer

from opspilot_api.db.migrations import alembic_config
from opspilot_api.events.producer import KafkaProducer


@pytest.fixture(scope="session")
def migrated_database_url() -> Iterator[str]:
    """A PostgreSQL container with all migrations applied, shared by the session."""
    with PostgresContainer("pgvector/pgvector:0.8.0-pg17", driver="psycopg") as container:
        url = container.get_connection_url()
        command.upgrade(alembic_config(url), "head")
        yield url


@pytest.fixture(scope="session")
def broker() -> Iterator[str]:
    """A Redpanda broker, started only by the event tests that ask for it."""
    with RedpandaContainer("docker.redpanda.com/redpandadata/redpanda:v24.2.18") as redpanda:
        yield redpanda.get_bootstrap_server()


@pytest.fixture
async def sessions(migrated_database_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_database_url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def producer(broker: str) -> AsyncIterator[KafkaProducer]:
    p = KafkaProducer(broker)
    yield p
    await p.aclose()
