"""/api/v1/me end to end: token verification, provisioning, and access rules."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import sqlalchemy as sa
from asgi_lifespan import LifespanManager
from fastapi import FastAPI

from opspilot_api.auth.dependencies import get_token_verifier
from opspilot_api.auth.tokens import TokenVerifier
from opspilot_api.config import Settings
from opspilot_api.main import create_app
from tests.support.tokens import AUDIENCE, ISSUER, TokenFactory

pytestmark = pytest.mark.integration


@pytest.fixture
def factory() -> TokenFactory:
    return TokenFactory()


@pytest.fixture
async def client(
    migrated_database_url: str, factory: TokenFactory
) -> AsyncIterator[httpx.AsyncClient]:
    async def resolve(_token: str) -> Any:
        return factory.public_key

    app: FastAPI = create_app(
        Settings(
            app_env="test",
            database_url=migrated_database_url,
            redis_url="redis://unused:6379/0",
            jwt_issuer=ISSUER,
            jwt_audience=AUDIENCE,
        )
    )
    verifier = TokenVerifier(issuer=ISSUER, audience=AUDIENCE, key_resolver=resolve)
    app.dependency_overrides[get_token_verifier] = lambda: verifier
    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.fixture
def engine(migrated_database_url: str) -> Any:
    eng = sa.create_engine(migrated_database_url)
    yield eng
    eng.dispose()


def unique() -> str:
    return uuid.uuid4().hex[:12]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_missing_token_is_401_with_challenge(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/me")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json() == {"detail": "Not authenticated"}


async def test_non_bearer_scheme_is_401(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/me", headers={"Authorization": "Basic dXNlcjpwdw=="})

    assert response.status_code == 401


@pytest.mark.parametrize(
    "overrides",
    [{"aud": "other"}, {"iss": "https://evil.test"}, {"exp": 1}],
    ids=["audience", "issuer", "expired"],
)
async def test_invalid_token_is_401_without_details(
    client: httpx.AsyncClient, factory: TokenFactory, overrides: dict[str, Any]
) -> None:
    response = await client.get("/api/v1/me", headers=auth(factory.token(**overrides)))

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == 'Bearer error="invalid_token"'
    assert response.json() == {"detail": "Not authenticated"}


async def test_first_login_provisions_organization_and_user(
    client: httpx.AsyncClient, factory: TokenFactory, engine: sa.Engine
) -> None:
    org, sub = f"org-{unique()}", unique()

    response = await client.get(
        "/api/v1/me", headers=auth(factory.token(sub=sub, organization=org))
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["organization"]["slug"] == org
    assert body["roles"] == ["incident-commander"]
    assert body["display_name"] == "Cleo Commander"
    with engine.connect() as conn:
        assert (
            conn.execute(
                sa.text("SELECT count(*) FROM users WHERE external_auth_id = :s"), {"s": sub}
            ).scalar_one()
            == 1
        )
        assert (
            conn.execute(
                sa.text("SELECT count(*) FROM organizations WHERE slug = :o"), {"o": org}
            ).scalar_one()
            == 1
        )


async def test_later_logins_reuse_records_and_refresh_roles(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    org, sub = f"org-{unique()}", unique()
    first = await client.get("/api/v1/me", headers=auth(factory.token(sub=sub, organization=org)))

    second = await client.get(
        "/api/v1/me",
        headers=auth(
            factory.token(sub=sub, organization=org, realm_access={"roles": ["viewer", "operator"]})
        ),
    )

    assert second.json()["id"] == first.json()["id"]
    assert second.json()["organization"]["id"] == first.json()["organization"]["id"]
    assert second.json()["roles"] == ["operator", "viewer"]


async def test_user_cannot_switch_organization(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    sub = unique()
    await client.get(
        "/api/v1/me", headers=auth(factory.token(sub=sub, organization=f"a-{unique()}"))
    )

    response = await client.get(
        "/api/v1/me", headers=auth(factory.token(sub=sub, organization=f"b-{unique()}"))
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}


async def test_disabled_user_is_403(
    client: httpx.AsyncClient, factory: TokenFactory, engine: sa.Engine
) -> None:
    org, sub = f"org-{unique()}", unique()
    token = factory.token(sub=sub, organization=org)
    await client.get("/api/v1/me", headers=auth(token))
    with engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE users SET status = 'disabled' WHERE external_auth_id = :s"), {"s": sub}
        )

    response = await client.get("/api/v1/me", headers=auth(token))

    assert response.status_code == 403


async def test_concurrent_first_logins_create_one_user(
    client: httpx.AsyncClient, factory: TokenFactory, engine: sa.Engine
) -> None:
    org, sub = f"org-{unique()}", unique()
    token = factory.token(sub=sub, organization=org)

    responses = await asyncio.gather(
        *(client.get("/api/v1/me", headers=auth(token)) for _ in range(8))
    )

    assert {r.status_code for r in responses} == {200}
    assert len({r.json()["id"] for r in responses}) == 1
    with engine.connect() as conn:
        assert (
            conn.execute(
                sa.text("SELECT count(*) FROM users WHERE external_auth_id = :s"), {"s": sub}
            ).scalar_one()
            == 1
        )


async def test_identity_provider_outage_is_503(migrated_database_url: str) -> None:
    app = create_app(
        Settings(
            app_env="test",
            database_url=migrated_database_url,
            redis_url="redis://unused:6379/0",
            jwt_issuer="http://127.0.0.1:1/realms/opspilot",
            jwt_audience=AUDIENCE,
        )
    )
    token = TokenFactory().token(iss="http://127.0.0.1:1/realms/opspilot")
    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            response = await c.get("/api/v1/me", headers=auth(token))

    assert response.status_code == 503
