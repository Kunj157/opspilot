from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine

from opspilot_api import readiness
from opspilot_api.config import Settings, get_settings
from opspilot_api.logging import configure_logging
from opspilot_api.request_context import RequestContextMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        checks: dict[str, readiness.ReadinessCheck] = {}
        async with AsyncExitStack() as stack:
            if settings.database_url:
                engine = create_async_engine(settings.database_url, pool_pre_ping=True)
                stack.push_async_callback(engine.dispose)
                checks["database"] = readiness.database_check(engine)
            if settings.redis_url:
                redis = Redis.from_url(
                    settings.redis_url,
                    socket_connect_timeout=settings.readiness_timeout_seconds,
                    socket_timeout=settings.readiness_timeout_seconds,
                )
                stack.push_async_callback(redis.aclose)
                checks["redis"] = readiness.redis_check(redis)

            app.state.settings = settings
            app.state.readiness_checks = checks
            yield

    app = FastAPI(title="OpsPilot API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(readiness.router)
    return app
