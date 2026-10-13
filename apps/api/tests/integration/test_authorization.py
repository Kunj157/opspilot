"""require() and tenant scoping on real routes and a real database."""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.auth.dependencies import CurrentPrincipal, get_token_verifier
from opspilot_api.auth.permissions import Permission, require
from opspilot_api.auth.principal import Principal
from opspilot_api.auth.tenancy import get_owned_or_404
from opspilot_api.auth.tokens import TokenVerifier
from opspilot_api.config import Settings
from opspilot_api.db.models import User
from opspilot_api.db.session import get_session
from opspilot_api.main import create_app
from tests.support.tokens import AUDIENCE, ISSUER, TokenFactory

pytestmark = pytest.mark.integration

probe = APIRouter(prefix="/probe")


@probe.post("/approve")
async def approve(
    principal: Annotated[Principal, Depends(require(Permission.APPROVE_REMEDIATION))],
) -> dict[str, str]:
    return {"approved_by": str(principal.user_id)}


@probe.get("/users/{user_id}")
async def read_user(
    user_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require(Permission.VIEW_SERVICES))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    user = await get_owned_or_404(session, User, user_id, principal)
    return {"id": str(user.id)}


@probe.get("/whoami")
async def whoami(principal: CurrentPrincipal) -> dict[str, str]:
    return {"id": str(principal.user_id)}


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
    app.include_router(probe)
    verifier = TokenVerifier(issuer=ISSUER, audience=AUDIENCE, key_resolver=resolve)
    app.dependency_overrides[get_token_verifier] = lambda: verifier
    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


def headers(factory: TokenFactory, org: str, *roles: str, sub: str | None = None) -> dict[str, str]:
    token = factory.token(
        sub=sub or uuid.uuid4().hex, organization=org, realm_access={"roles": list(roles)}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    ("roles", "expected"),
    [
        ((), 403),
        (("viewer",), 403),
        (("operator",), 403),
        (("incident-commander",), 200),
        (("administrator",), 200),
        (("viewer", "incident-commander"), 200),
    ],
)
async def test_approve_requires_incident_commander_or_admin(
    client: httpx.AsyncClient, factory: TokenFactory, roles: tuple[str, ...], expected: int
) -> None:
    response = await client.post("/probe/approve", headers=headers(factory, "acme", *roles))

    assert response.status_code == expected
    if expected == 403:
        assert response.json() == {"detail": "Forbidden"}


async def test_unauthenticated_is_401_not_403(client: httpx.AsyncClient) -> None:
    response = await client.post("/probe/approve")

    assert response.status_code == 401


async def test_user_without_application_roles_can_still_identify(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    response = await client.get("/probe/whoami", headers=headers(factory, "acme"))

    assert response.status_code == 200


async def test_same_organization_resource_is_visible(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    org = f"org-{uuid.uuid4().hex[:8]}"
    owner_id = (await client.get("/probe/whoami", headers=headers(factory, org, "viewer"))).json()[
        "id"
    ]

    response = await client.get(f"/probe/users/{owner_id}", headers=headers(factory, org, "viewer"))

    assert response.status_code == 200


async def test_cross_organization_resource_is_404(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    victim_org, attacker_org = f"v-{uuid.uuid4().hex[:8]}", f"a-{uuid.uuid4().hex[:8]}"
    victim_id = (
        await client.get("/probe/whoami", headers=headers(factory, victim_org, "viewer"))
    ).json()["id"]

    response = await client.get(
        f"/probe/users/{victim_id}", headers=headers(factory, attacker_org, "administrator")
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


async def test_missing_resource_is_indistinguishable_from_foreign(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    response = await client.get(
        f"/probe/users/{uuid.uuid4()}", headers=headers(factory, "acme", "viewer")
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


async def test_me_lists_effective_permissions(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    response = await client.get("/api/v1/me", headers=headers(factory, "acme", "operator"))

    assert response.json()["permissions"] == [
        "manage_runbooks",
        "start_investigation",
        "view_incidents",
        "view_services",
    ]
