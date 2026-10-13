"""Real Keycloak with the repository realm: tokens it issues are accepted end to end."""

import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from asgi_lifespan import LifespanManager
from testcontainers.core.container import DockerContainer

from opspilot_api.config import Settings
from opspilot_api.main import create_app

pytestmark = pytest.mark.integration

REALM_FILE = Path(__file__).resolve().parents[4] / "infrastructure/keycloak/realm-opspilot.json"


@pytest.fixture(scope="module")
def keycloak_url() -> Iterator[str]:
    container = (
        DockerContainer("quay.io/keycloak/keycloak:26.7.5")
        .with_command("start-dev --import-realm")
        .with_env("KC_HEALTH_ENABLED", "true")
        .with_volume_mapping(str(REALM_FILE), "/opt/keycloak/data/import/realm-opspilot.json", "ro")
        .with_exposed_ports(8080, 9000)
    )
    with container:
        host = container.get_container_host_ip()
        health = f"http://{host}:{container.get_exposed_port(9000)}/health/ready"
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                if httpx.get(health, timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            pytest.fail("Keycloak did not become ready")
        yield f"http://{host}:{container.get_exposed_port(8080)}"


def password_token(keycloak_url: str, username: str) -> str:
    response = httpx.post(
        f"{keycloak_url}/realms/opspilot/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "opspilot-dev-cli",
            "username": username,
            "password": "opspilot-dev",
        },
        timeout=10,
    )
    response.raise_for_status()
    token: str = response.json()["access_token"]
    return token


@pytest.fixture
async def client(migrated_database_url: str, keycloak_url: str) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        Settings(
            app_env="test",
            database_url=migrated_database_url,
            redis_url="redis://unused:6379/0",
            jwt_issuer=f"{keycloak_url}/realms/opspilot",
            jwt_audience="opspilot-api",
        )
    )
    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.mark.parametrize(
    ("username", "organization", "role"),
    [
        ("viewer", "acme", "viewer"),
        ("commander", "acme", "incident-commander"),
        ("outsider", "globex", "administrator"),
    ],
)
async def test_keycloak_token_authenticates(
    client: httpx.AsyncClient, keycloak_url: str, username: str, organization: str, role: str
) -> None:
    token = password_token(keycloak_url, username)

    response = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["organization"]["slug"] == organization
    assert body["roles"] == [role]
    assert body["email"] == f"{username}@{organization}.example"


async def test_tampered_keycloak_token_is_rejected(
    client: httpx.AsyncClient, keycloak_url: str
) -> None:
    header, payload, signature = password_token(keycloak_url, "viewer").split(".")
    tampered = f"{header}.{payload}.{signature[:-4]}AAAA"

    response = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {tampered}"})

    assert response.status_code == 401
