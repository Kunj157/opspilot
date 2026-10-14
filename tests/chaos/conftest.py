"""Fixtures for the chaos suite (docs/operations/chaos-results.md).

Run with `make test-chaos`: from apps/api, so the API package and its test
helpers are importable. Containers are bound to fixed free host ports so a
restart keeps its address, as a managed database or cache would.
"""

from collections.abc import Iterator

import pytest
from alembic import command
from opspilot_api.db.migrations import alembic_config
from testcontainers.community.kafka import RedpandaContainer
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer
from tests.support.tokens import TokenFactory

from chaos.harness import POSTGRES_IMAGE, REDIS_IMAGE, REDPANDA_IMAGE, Controlled, free_port


@pytest.fixture(scope="module")
def postgres() -> Iterator[Controlled]:
    """A migrated PostgreSQL on a fixed port, one per test module (they get restarted)."""
    port = free_port()
    with PostgresContainer(POSTGRES_IMAGE, driver="psycopg").with_bind_ports(5432, port) as pg:
        url = pg.get_connection_url()
        command.upgrade(alembic_config(url), "head")
        controlled = Controlled(pg, url)
        yield controlled
        controlled.ensure_running()


@pytest.fixture(scope="module")
def redis() -> Iterator[Controlled]:
    port = free_port()
    with RedisContainer(REDIS_IMAGE).with_bind_ports(6379, port) as container:
        controlled = Controlled(container, f"redis://127.0.0.1:{port}/0")
        yield controlled
        controlled.ensure_running()


@pytest.fixture(scope="module")
def tokens() -> TokenFactory:
    return TokenFactory()


@pytest.fixture(scope="module")
def redpanda() -> Iterator[Controlled]:
    """A broker we pause (ports survive a pause, not a restart: Redpanda advertises them)."""
    with RedpandaContainer(REDPANDA_IMAGE) as container:
        controlled = Controlled(container, container.get_bootstrap_server())
        yield controlled
        controlled.ensure_running()
