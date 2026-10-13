"""Liveness and readiness endpoints.

Liveness (`/health`) only proves the process answers. Readiness (`/ready`)
verifies required configuration and every downstream dependency, each with
its own timeout, and never exposes exception details to the caller.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from opspilot_api.config import Settings

ReadinessCheck = Callable[[], Awaitable[None]]

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]


class CheckResult(BaseModel):
    status: Literal["ok", "fail"]
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, CheckResult]


def database_check(engine: AsyncEngine) -> ReadinessCheck:
    async def check() -> None:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    return check


def redis_check(client: Redis) -> ReadinessCheck:
    async def check() -> None:
        if not await client.ping():
            raise ConnectionError("redis ping returned false")

    return check


def get_readiness_checks(request: Request) -> dict[str, ReadinessCheck]:
    checks: dict[str, ReadinessCheck] = request.app.state.readiness_checks
    return checks


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def _run_check(name: str, check: ReadinessCheck, timeout_seconds: float) -> CheckResult:
    try:
        async with asyncio.timeout(timeout_seconds):
            await check()
    except TimeoutError:
        logger.warning("readiness check timed out", check=name, timeout_seconds=timeout_seconds)
        return CheckResult(status="fail", detail="timeout")
    except Exception as exc:
        logger.warning("readiness check failed", check=name, error_type=type(exc).__name__)
        return CheckResult(status="fail", detail="unavailable")
    return CheckResult(status="ok")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
async def ready(
    response: Response,
    settings: Annotated[Settings, Depends(get_app_settings)],
    checks: Annotated[dict[str, ReadinessCheck], Depends(get_readiness_checks)],
) -> ReadinessResponse:
    missing = settings.missing_required()
    results = {
        "config": CheckResult(
            status="fail" if missing else "ok",
            detail=f"missing: {', '.join(missing)}" if missing else None,
        )
    }
    names = sorted(checks)
    outcomes = await asyncio.gather(
        *(_run_check(name, checks[name], settings.readiness_timeout_seconds) for name in names)
    )
    results.update(zip(names, outcomes, strict=True))

    is_ready = all(result.status == "ok" for result in results.values())
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="ready" if is_ready else "not_ready", checks=results)
