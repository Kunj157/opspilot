"""Redis-backed API rate limits.

Fixed windows counted in Redis, so every API replica shares one budget:
- requests without a bearer token: per client IP (`anonymous`);
- rejected tokens: per client IP, a small budget (`auth_failure`); once it is
  spent, further tokens from that IP are refused before verification;
- authenticated requests: per user, with separate budgets for reads, mutations
  (`write`), and sensitive actions (`sensitive`: approvals, model promotion,
  agent runs, reindexing).

Over a limit the API answers 429 with Retry-After, logs a warning, and counts
`http_rate_limited_total`. If Redis is unreachable the limiter fails open for a
short back-off: a cache outage must not take the API down.
"""

import math
import time
from dataclasses import dataclass
from enum import StrEnum

import structlog
from fastapi import HTTPException, Request, status
from prometheus_client import Counter
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from opspilot_api.config import Settings

SERVICE = "opspilot-api"
RATE_LIMITED = Counter(
    "http_rate_limited_total", "Requests rejected by a rate limit", ["service", "policy"]
)
EXEMPT_PATHS = frozenset({"/api/v1/health", "/api/v1/ready", "/metrics"})
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# Route templates ending in these segments approve changes or start paid agent work.
SENSITIVE_SUFFIXES = (
    "/approve",
    "/reject",
    "/promote",
    "/investigation",
    "/postmortem",
    "/reindex",
)
FAILURE_BACKOFF_SECONDS = 5.0

logger = structlog.get_logger()


class Policy(StrEnum):
    ANONYMOUS = "anonymous"
    AUTH_FAILURE = "auth_failure"
    READ = "read"
    WRITE = "write"
    SENSITIVE = "sensitive"


@dataclass(frozen=True)
class Decision:
    allowed: bool
    retry_after: int = 0


def classify(method: str, route_path: str) -> Policy:
    if method not in MUTATING_METHODS:
        return Policy.READ
    if route_path.endswith(SENSITIVE_SUFFIXES):
        return Policy.SENSITIVE
    return Policy.WRITE


class RateLimiter:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._window = settings.rate_limit_window_seconds
        self._limits = {
            Policy.ANONYMOUS: settings.rate_limit_anonymous,
            Policy.AUTH_FAILURE: settings.rate_limit_auth_failures,
            Policy.READ: settings.rate_limit_read,
            Policy.WRITE: settings.rate_limit_write,
            Policy.SENSITIVE: settings.rate_limit_sensitive,
        }
        self._unavailable_until = 0.0

    def _key(self, policy: Policy, identity: str, now: float) -> str:
        return f"ratelimit:{policy}:{identity}:{int(now // self._window)}"

    def _retry_after(self, now: float) -> int:
        window_end = (now // self._window + 1) * self._window
        return max(1, math.ceil(window_end - now))

    def _redis_failed(self, exc: Exception) -> None:
        self._unavailable_until = time.monotonic() + FAILURE_BACKOFF_SECONDS
        logger.warning("rate limiter unavailable, allowing requests", error=type(exc).__name__)

    def _skip(self) -> bool:
        return time.monotonic() < self._unavailable_until

    async def hit(self, policy: Policy, identity: str) -> Decision:
        """Count one request against `identity`'s budget for `policy`."""
        if self._skip():
            return Decision(True)
        now = time.time()
        key = self._key(policy, identity, now)
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                pipe.expire(key, self._window + 1)
                count, _ = await pipe.execute()
        except (RedisError, OSError) as exc:
            self._redis_failed(exc)
            return Decision(True)
        if int(count) <= self._limits[policy]:
            return Decision(True)
        return self._deny(policy, now)

    async def exhausted(self, policy: Policy, identity: str) -> Decision:
        """Check the budget without counting (refuse before doing the work)."""
        if self._skip():
            return Decision(True)
        now = time.time()
        try:
            count = await self._redis.get(self._key(policy, identity, now))
        except (RedisError, OSError) as exc:
            self._redis_failed(exc)
            return Decision(True)
        if count is None or int(count) < self._limits[policy]:
            return Decision(True)
        return self._deny(policy, now)

    def _deny(self, policy: Policy, now: float) -> Decision:
        decision = Decision(False, self._retry_after(now))
        RATE_LIMITED.labels(SERVICE, policy.value).inc()
        logger.warning(
            "rate limit exceeded",
            policy=policy.value,
            limit=self._limits[policy],
            window_seconds=self._window,
            retry_after=decision.retry_after,
        )
        return decision


DETAIL = "Too many requests"


def too_many_requests(decision: Decision) -> HTTPException:
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        DETAIL,
        headers={"Retry-After": str(decision.retry_after)},
    )


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def get_rate_limiter(request: Request) -> RateLimiter | None:
    limiter: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
    return limiter


async def enforce_principal_limit(request: Request, user_id: str) -> None:
    limiter = get_rate_limiter(request)
    if limiter is None:
        return
    route = request.scope.get("route")
    policy = classify(request.method, str(getattr(route, "path", request.url.path)))
    decision = await limiter.hit(policy, user_id)
    if not decision.allowed:
        raise too_many_requests(decision)


class AnonymousRateLimitMiddleware:
    """Per-IP budget for requests that carry no bearer token.

    Authenticated requests are limited per user after the token is verified
    (see `auth.dependencies.get_principal`).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return
        limiter: RateLimiter | None = getattr(scope["app"].state, "rate_limiter", None)
        headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        has_token = any(name.lower() == b"authorization" for name, _ in headers)
        if limiter is not None and not has_token:
            client = scope.get("client")
            decision = await limiter.hit(Policy.ANONYMOUS, client[0] if client else "unknown")
            if not decision.allowed:
                response = JSONResponse(
                    {"detail": DETAIL},
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    headers={"Retry-After": str(decision.retry_after)},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
