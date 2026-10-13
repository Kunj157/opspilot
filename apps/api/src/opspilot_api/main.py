from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from opspilot_api import readiness
from opspilot_api.audit.middleware import AuditMiddleware
from opspilot_api.auth.tokens import TokenVerifier, discovered_key_resolver
from opspilot_api.config import Settings, get_settings
from opspilot_api.db.session import SessionFactory
from opspilot_api.events.broker import EventBroker
from opspilot_api.logging import configure_logging
from opspilot_api.request_context import RequestContextMiddleware
from opspilot_api.routes import audit_logs, incident_streams, incidents, me, services, topology


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        checks: dict[str, readiness.ReadinessCheck] = {}
        session_factory: SessionFactory | None = None
        token_verifier: TokenVerifier | None = None
        event_broker: EventBroker | None = None
        async with AsyncExitStack() as stack:
            if settings.database_url:
                engine = create_async_engine(settings.database_url, pool_pre_ping=True)
                stack.push_async_callback(engine.dispose)
                checks["database"] = readiness.database_check(engine)
                session_factory = async_sessionmaker(engine, expire_on_commit=False)
                event_broker = EventBroker(settings.database_url)
                event_broker.start()
                stack.push_async_callback(event_broker.stop)
            if settings.jwt_issuer and settings.jwt_audience:
                token_verifier = TokenVerifier(
                    issuer=settings.jwt_issuer,
                    audience=settings.jwt_audience,
                    key_resolver=discovered_key_resolver(settings.jwt_issuer),
                )
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
            app.state.session_factory = session_factory
            app.state.token_verifier = token_verifier
            app.state.event_broker = event_broker
            yield

    app = FastAPI(title="OpsPilot API", version=version("opspilot-api"), lifespan=lifespan)
    # Last added runs first: request context wraps auditing, so audit
    # records carry the request ID and client IP.
    app.add_middleware(AuditMiddleware)
    app.add_middleware(RequestContextMiddleware)
    # Outermost: take the client address from X-Forwarded-For only when the
    # connection comes from a trusted proxy, so direct callers cannot spoof it.
    app.add_middleware(
        ProxyHeadersMiddleware,
        trusted_hosts=[
            host.strip() for host in settings.trusted_proxies.split(",") if host.strip()
        ],
    )
    app.include_router(readiness.router)
    app.include_router(me.router)
    app.include_router(audit_logs.router)
    app.include_router(services.router)
    app.include_router(topology.router)
    # Before incidents.router, so /incidents/stream is not read as an incident ID.
    app.include_router(incident_streams.router)
    app.include_router(incidents.router)
    return app
