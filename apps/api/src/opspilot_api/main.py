from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from opspilot_api import http_metrics, ops_metrics, readiness
from opspilot_api.audit.middleware import AuditMiddleware
from opspilot_api.auth.tokens import TokenVerifier, discovered_key_resolver
from opspilot_api.config import Settings, get_settings
from opspilot_api.db.session import SessionFactory
from opspilot_api.events.broker import EventBroker
from opspilot_api.http_metrics import MetricsMiddleware
from opspilot_api.logging import configure_logging
from opspilot_api.rate_limit import AnonymousRateLimitMiddleware, RateLimiter
from opspilot_api.request_context import RequestContextMiddleware
from opspilot_api.routes import (
    audit_logs,
    detections,
    evaluations,
    incident_metrics,
    incident_streams,
    incidents,
    investigations,
    me,
    ml,
    remediation,
    runbooks,
    services,
    topology,
    users,
)
from opspilot_api.runbooks.embeddings import build_embedder
from opspilot_api.security_headers import SecurityHeadersMiddleware, add_cors


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        checks: dict[str, readiness.ReadinessCheck] = {}
        session_factory: SessionFactory | None = None
        token_verifier: TokenVerifier | None = None
        event_broker: EventBroker | None = None
        rate_limiter: RateLimiter | None = None
        async with AsyncExitStack() as stack:
            if settings.database_url:
                engine = create_async_engine(settings.database_url, pool_pre_ping=True)
                stack.push_async_callback(engine.dispose)
                checks["database"] = readiness.database_check(engine)
                ops_metrics.POOLS.track("api", engine)
                stack.callback(ops_metrics.POOLS.untrack, "api")
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
                if settings.rate_limit_enabled:
                    rate_limiter = RateLimiter(redis, settings)

            app.state.embedder = build_embedder(
                settings.embedding_model, settings.embedding_cache_dir
            )
            app.state.settings = settings
            app.state.readiness_checks = checks
            app.state.session_factory = session_factory
            app.state.token_verifier = token_verifier
            app.state.event_broker = event_broker
            app.state.rate_limiter = rate_limiter
            yield

    app = FastAPI(title="OpsPilot API", version=version("opspilot-api"), lifespan=lifespan)
    # Last added runs first: request context wraps auditing, so audit
    # records carry the request ID and client IP; rate-limit rejections are
    # logged and counted like any other response.
    app.add_middleware(AnonymousRateLimitMiddleware)
    app.add_middleware(AuditMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestContextMiddleware)
    # Every response, including errors and CORS preflights, gets the headers.
    add_cors(app, settings)
    app.add_middleware(SecurityHeadersMiddleware)
    # Outermost: take the client address from X-Forwarded-For only when the
    # connection comes from a trusted proxy, so direct callers cannot spoof it.
    app.add_middleware(
        ProxyHeadersMiddleware,
        trusted_hosts=[
            host.strip() for host in settings.trusted_proxies.split(",") if host.strip()
        ],
    )
    app.add_route("/metrics", http_metrics.metrics, include_in_schema=False)
    app.include_router(readiness.router)
    app.include_router(me.router)
    app.include_router(users.router)
    app.include_router(audit_logs.router)
    app.include_router(services.router)
    app.include_router(topology.router)
    # Before incidents.router, so /incidents/stream is not read as an incident ID.
    app.include_router(incident_streams.router)
    app.include_router(incidents.router)
    app.include_router(incident_metrics.router)
    app.include_router(evaluations.router)
    app.include_router(detections.router)
    app.include_router(investigations.router)
    app.include_router(remediation.router)
    app.include_router(runbooks.router)
    app.include_router(ml.router)
    return app
