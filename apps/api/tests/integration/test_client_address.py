"""Audit records carry the real client address, and only a trusted proxy may forward one."""

import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
import sqlalchemy as sa
from asgi_lifespan import LifespanManager
from fastapi import APIRouter

from opspilot_api.auth.dependencies import CurrentPrincipal, get_token_verifier
from opspilot_api.auth.tokens import TokenVerifier
from opspilot_api.config import Settings
from opspilot_api.main import create_app
from tests.support.tokens import AUDIENCE, ISSUER, TokenFactory

pytestmark = pytest.mark.integration

probe = APIRouter(prefix="/probe")


@probe.post("/touch")
async def touch(principal: CurrentPrincipal) -> dict[str, str]:
    return {"ok": "yes"}


ClientFactory = Callable[[str], Any]


@pytest.fixture
def factory() -> TokenFactory:
    return TokenFactory()


@pytest.fixture
def connect_from(migrated_database_url: str, factory: TokenFactory) -> ClientFactory:
    @asynccontextmanager
    async def connect(peer: str) -> AsyncIterator[httpx.AsyncClient]:
        async def resolve(_token: str) -> Any:
            return factory.public_key

        app = create_app(
            Settings(
                app_env="test",
                database_url=migrated_database_url,
                redis_url="redis://unused:6379/0",
                jwt_issuer=ISSUER,
                jwt_audience=AUDIENCE,
                trusted_proxies="10.0.0.5",
            )
        )
        app.include_router(probe)
        verifier = TokenVerifier(issuer=ISSUER, audience=AUDIENCE, key_resolver=resolve)
        app.dependency_overrides[get_token_verifier] = lambda: verifier
        async with LifespanManager(app) as manager:
            transport = httpx.ASGITransport(app=manager.app, client=(peer, 40000))
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
                yield c

    return connect


def recorded_address(database_url: str, actor_sub: str) -> str:
    engine = sa.create_engine(database_url)
    try:
        with engine.connect() as conn:
            return str(
                conn.execute(
                    sa.text(
                        "SELECT a.ip_address FROM audit_logs a"
                        " JOIN users u ON u.id::text = a.actor_id"
                        " WHERE u.external_auth_id = :sub AND a.action = 'http.post'"
                    ),
                    {"sub": actor_sub},
                ).scalar_one()
            )
    finally:
        engine.dispose()


async def post_as_new_user(client: httpx.AsyncClient, factory: TokenFactory, **headers: str) -> str:
    sub = uuid.uuid4().hex
    token = factory.token(sub=sub, organization=f"org-{sub[:8]}")
    response = await client.post(
        "/probe/touch", headers={"Authorization": f"Bearer {token}", **headers}
    )
    assert response.status_code == 200
    return sub


async def test_trusted_proxy_forwards_the_browser_address(
    connect_from: ClientFactory, factory: TokenFactory, migrated_database_url: str
) -> None:
    async with connect_from("10.0.0.5") as client:
        sub = await post_as_new_user(client, factory, **{"X-Forwarded-For": "198.51.100.23"})

    assert recorded_address(migrated_database_url, sub) == "198.51.100.23"


async def test_direct_caller_cannot_spoof_its_address(
    connect_from: ClientFactory, factory: TokenFactory, migrated_database_url: str
) -> None:
    async with connect_from("203.0.113.66") as client:
        sub = await post_as_new_user(client, factory, **{"X-Forwarded-For": "1.2.3.4"})

    assert recorded_address(migrated_database_url, sub) == "203.0.113.66"


async def test_spoofed_hop_before_the_proxy_is_ignored(
    connect_from: ClientFactory, factory: TokenFactory, migrated_database_url: str
) -> None:
    # The browser sent its own forged X-Forwarded-For; the proxy appended the real address.
    async with connect_from("10.0.0.5") as client:
        sub = await post_as_new_user(
            client, factory, **{"X-Forwarded-For": "1.2.3.4, 198.51.100.77"}
        )

    assert recorded_address(migrated_database_url, sub) == "198.51.100.77"
