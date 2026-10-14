"""Redis-backed rate limits (plan §25): per user, per IP, 429 with Retry-After."""

import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
from prometheus_client import REGISTRY
from redis import Redis
from testcontainers.community.redis import RedisContainer

from tests.support.app import Caller, api_client, new_org
from tests.support.tokens import TokenFactory, new_key

pytestmark = pytest.mark.integration

PEER = "203.0.113.7"
# Long windows: a test never straddles a window boundary.
LIMITS: dict[str, Any] = {
    "rate_limit_enabled": True,
    "rate_limit_window_seconds": 3600,
    "rate_limit_read": 5,
    "rate_limit_write": 3,
    "rate_limit_sensitive": 1,
    "rate_limit_anonymous": 4,
    "rate_limit_auth_failures": 2,
    # Lets tests choose the client IP through X-Forwarded-For.
    "trusted_proxies": PEER,
}


@pytest.fixture(scope="module")
def redis_url() -> Iterator[str]:
    with RedisContainer("redis:7.4-alpine") as container:
        host = container.get_container_host_ip()
        yield f"redis://{host}:{container.get_exposed_port(6379)}/0"


@pytest.fixture
def factory() -> TokenFactory:
    return TokenFactory()


@pytest.fixture
async def client(
    migrated_database_url: str, factory: TokenFactory, redis_url: str
) -> AsyncIterator[httpx.AsyncClient]:
    Redis.from_url(redis_url).flushdb()
    async with api_client(
        migrated_database_url, factory, peer=PEER, redis_url=redis_url, **LIMITS
    ) as c:
        yield c


def limited(policy: str) -> float:
    value = REGISTRY.get_sample_value(
        "http_rate_limited_total", {"service": "opspilot-api", "policy": policy}
    )
    return value or 0.0


def from_ip() -> dict[str, str]:
    return {"X-Forwarded-For": f"198.51.100.{uuid.uuid4().int % 250 + 1}"}


def assert_limited(response: httpx.Response) -> None:
    assert response.status_code == 429
    assert response.json() == {"detail": "Too many requests"}
    assert 0 < int(response.headers["Retry-After"]) <= 3600
    assert response.headers["X-Request-ID"]


async def test_reads_over_the_budget_get_429_with_retry_after(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    caller = Caller(factory, new_org(), "viewer")
    before = limited("read")

    statuses = [
        (await client.get("/api/v1/incidents", headers=caller.headers)).status_code
        for _ in range(5)
    ]
    rejected = await client.get("/api/v1/incidents", headers=caller.headers)

    assert statuses == [200] * 5
    assert_limited(rejected)
    assert limited("read") == before + 1


async def test_mutations_have_a_stricter_budget_than_reads(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    caller = Caller(factory, new_org(), "operator")
    body = {"title": "Checkout errors", "severity": "low"}

    created = [
        (await client.post("/api/v1/incidents", json=body, headers=caller.headers)).status_code
        for _ in range(3)
    ]
    rejected = await client.post("/api/v1/incidents", json=body, headers=caller.headers)
    still_readable = await client.get("/api/v1/incidents", headers=caller.headers)

    assert created == [201] * 3
    assert_limited(rejected)
    assert still_readable.status_code == 200


async def test_sensitive_actions_are_limited_before_the_handler_runs(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    caller = Caller(factory, new_org(), "incident-commander")
    path = f"/api/v1/proposals/{uuid.uuid4()}/approve"
    before = limited("sensitive")

    first = await client.post(path, json={"version": 1}, headers=caller.headers)
    second = await client.post(path, json={"version": 1}, headers=caller.headers)

    assert first.status_code == 404
    assert_limited(second)
    assert limited("sensitive") == before + 1


async def test_budgets_are_per_user(client: httpx.AsyncClient, factory: TokenFactory) -> None:
    org = new_org()
    busy, other = Caller(factory, org, "viewer"), Caller(factory, org, "viewer")
    for _ in range(5):
        await client.get("/api/v1/me", headers=busy.headers)

    assert (await client.get("/api/v1/me", headers=busy.headers)).status_code == 429
    assert (await client.get("/api/v1/me", headers=other.headers)).status_code == 200


async def test_requests_without_a_token_are_limited_per_ip(client: httpx.AsyncClient) -> None:
    ip, other_ip = from_ip(), from_ip()
    before = limited("anonymous")

    statuses = [(await client.get("/api/v1/me", headers=ip)).status_code for _ in range(4)]
    rejected = await client.get("/api/v1/me", headers=ip)

    assert statuses == [401] * 4
    assert_limited(rejected)
    assert limited("anonymous") == before + 1
    assert (await client.get("/api/v1/me", headers=other_ip)).status_code == 401


async def test_health_and_readiness_are_never_limited(client: httpx.AsyncClient) -> None:
    ip = from_ip()

    statuses = {(await client.get("/api/v1/health", headers=ip)).status_code for _ in range(10)}

    assert statuses == {200}


async def test_rejected_tokens_are_limited_per_ip_even_for_valid_tokens_after(
    client: httpx.AsyncClient, factory: TokenFactory
) -> None:
    ip = from_ip()
    forged = {"Authorization": f"Bearer {factory.token(key=new_key())}", **ip}
    valid = {**Caller(factory, new_org(), "viewer").headers, **ip}
    before = limited("auth_failure")

    failures = [(await client.get("/api/v1/me", headers=forged)).status_code for _ in range(2)]
    blocked = await client.get("/api/v1/me", headers=valid)

    assert failures == [401, 401]
    assert_limited(blocked)
    assert limited("auth_failure") == before + 1
    assert (await client.get("/api/v1/me", headers={**valid, **from_ip()})).status_code == 200


async def test_limit_hits_are_logged(
    client: httpx.AsyncClient, factory: TokenFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    caller = Caller(factory, new_org(), "incident-commander")
    path = f"/api/v1/proposals/{uuid.uuid4()}/reject"
    for _ in range(2):
        await client.post(path, json={"version": 1}, headers=caller.headers)

    out = capsys.readouterr().out
    assert '"message": "rate limit exceeded"' in out
    assert '"policy": "sensitive"' in out


async def test_requests_are_allowed_when_redis_is_down(
    migrated_database_url: str, factory: TokenFactory
) -> None:
    caller = Caller(factory, new_org(), "viewer")
    async with api_client(
        migrated_database_url,
        factory,
        redis_url="redis://127.0.0.1:1/0",
        **{**LIMITS, "rate_limit_read": 1},
    ) as c:
        statuses = {
            (await c.get("/api/v1/me", headers=caller.headers)).status_code for _ in range(3)
        }

    assert statuses == {200}


async def test_limits_can_be_turned_off(
    migrated_database_url: str, factory: TokenFactory, redis_url: str
) -> None:
    caller = Caller(factory, new_org(), "viewer")
    async with api_client(
        migrated_database_url,
        factory,
        redis_url=redis_url,
        **{**LIMITS, "rate_limit_enabled": False},
    ) as c:
        statuses = {
            (await c.get("/api/v1/me", headers=caller.headers)).status_code for _ in range(8)
        }

    assert statuses == {200}
