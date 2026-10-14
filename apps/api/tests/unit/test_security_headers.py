"""Security headers and the CORS policy (plan §25)."""

import httpx
import pytest
from asgi_lifespan import LifespanManager
from pydantic import ValidationError

from opspilot_api.config import Settings
from opspilot_api.main import create_app

PREFLIGHT = {"Access-Control-Request-Method": "POST"}


async def call(
    settings: Settings, method: str, path: str, *, base_url: str = "http://test", **kw: object
) -> httpx.Response:
    app = create_app(settings)
    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            return await client.request(method, path, **kw)  # type: ignore[arg-type]


@pytest.fixture
async def health(client: httpx.AsyncClient) -> httpx.Response:
    return await client.get("/api/v1/health")


def test_every_response_is_hardened(health: httpx.Response) -> None:
    assert health.headers["X-Content-Type-Options"] == "nosniff"
    assert health.headers["X-Frame-Options"] == "DENY"
    assert health.headers["Referrer-Policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in health.headers["Content-Security-Policy"]
    assert "default-src 'none'" in health.headers["Content-Security-Policy"]


def test_json_responses_are_not_stored(health: httpx.Response) -> None:
    assert health.headers["Cache-Control"] == "no-store"


async def test_error_responses_are_hardened_too(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-store"


def test_hsts_is_not_sent_over_plain_http(health: httpx.Response) -> None:
    assert "Strict-Transport-Security" not in health.headers


async def test_hsts_is_sent_over_https(settings: Settings) -> None:
    response = await call(settings, "GET", "/api/v1/health", base_url="https://test")

    assert response.headers["Strict-Transport-Security"].startswith("max-age=63072000")


async def test_docs_keep_frame_protection_but_may_load_their_ui(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/docs")

    assert response.headers["Content-Security-Policy"] == "frame-ancestors 'none'"


async def test_cors_is_off_by_default(client: httpx.AsyncClient) -> None:
    simple = await client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
    preflight = await client.options(
        "/api/v1/incidents", headers={"Origin": "https://evil.example", **PREFLIGHT}
    )

    assert "Access-Control-Allow-Origin" not in simple.headers
    assert "Access-Control-Allow-Origin" not in preflight.headers


async def test_cors_allows_only_configured_origins(settings: Settings) -> None:
    configured = settings.model_copy(update={"cors_allowed_origins": "https://ops.example"})

    allowed = await call(
        configured,
        "OPTIONS",
        "/api/v1/incidents",
        headers={
            "Origin": "https://ops.example",
            "Access-Control-Request-Headers": "idempotency-key",
            **PREFLIGHT,
        },
    )
    denied = await call(
        configured,
        "OPTIONS",
        "/api/v1/incidents",
        headers={"Origin": "https://evil.example", **PREFLIGHT},
    )

    assert allowed.status_code == 200
    assert allowed.headers["Access-Control-Allow-Origin"] == "https://ops.example"
    assert "Access-Control-Allow-Credentials" not in allowed.headers
    assert allowed.headers["X-Frame-Options"] == "DENY"
    assert denied.status_code == 400
    assert "Access-Control-Allow-Origin" not in denied.headers


@pytest.mark.parametrize("value", ["*", "ops.example", "https://ops.example/path", "ftp://x"])
def test_cors_origins_must_be_explicit(value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(cors_allowed_origins=value)
