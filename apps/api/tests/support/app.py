"""An API client wired to a real database and locally signed tokens."""

import uuid
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from typing import Any

import httpx
from asgi_lifespan import LifespanManager
from fastapi import APIRouter

from opspilot_api.auth.dependencies import get_token_verifier
from opspilot_api.auth.tokens import TokenVerifier
from opspilot_api.config import Settings
from opspilot_api.main import create_app
from tests.support.tokens import AUDIENCE, ISSUER, TokenFactory


@asynccontextmanager
async def api_client(
    database_url: str,
    factory: TokenFactory,
    *,
    routers: Iterable[APIRouter] = (),
    peer: str = "203.0.113.7",
    **settings: Any,
) -> AsyncIterator[httpx.AsyncClient]:
    async def resolve(_token: str) -> Any:
        return factory.public_key

    app = create_app(
        Settings(
            app_env="test",
            database_url=database_url,
            redis_url=settings.pop("redis_url", "redis://unused:6379/0"),
            # Deterministic embeddings: no model download in tests.
            embedding_model=settings.pop("embedding_model", "hashing"),
            # Off unless a test asks: most tests have no Redis to count in.
            rate_limit_enabled=settings.pop("rate_limit_enabled", False),
            jwt_issuer=ISSUER,
            jwt_audience=AUDIENCE,
            **settings,
        )
    )
    for router in routers:
        app.include_router(router)
    verifier = TokenVerifier(issuer=ISSUER, audience=AUDIENCE, key_resolver=resolve)
    app.dependency_overrides[get_token_verifier] = lambda: verifier
    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app, client=(peer, 50000))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


def new_org() -> str:
    return f"org-{uuid.uuid4().hex[:10]}"


class Caller:
    """A user with a fresh subject in `org` holding `roles`."""

    def __init__(self, factory: TokenFactory, org: str, *roles: str) -> None:
        self.org = org
        self.sub = uuid.uuid4().hex
        token = factory.token(sub=self.sub, organization=org, realm_access={"roles": list(roles)})
        self.headers = {"Authorization": f"Bearer {token}"}
