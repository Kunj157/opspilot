"""Application factory shared by all five demo services."""

import asyncio
import logging
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.trace.export import SpanExporter
from opentelemetry.trace import Status, StatusCode
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.routing import Match

from opspilot_demo.downstream import Downstream
from opspilot_demo.routes import ROUTERS
from opspilot_demo.settings import Settings
from opspilot_demo.telemetry import Metrics, logger, tracer_provider

UNFAULTED = {"/healthz", "/metrics"}


def _route(request: Request) -> str:
    for route in request.app.router.routes:
        if route.matches(request.scope)[0] is Match.FULL:
            return str(getattr(route, "path", request.url.path))
    return "unmatched"


def create_app(
    settings: Settings,
    *,
    span_exporter: SpanExporter | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    rng: random.Random | None = None,
) -> FastAPI:
    provider = tracer_provider(settings, span_exporter)
    metrics = Metrics()
    chance = rng or random.Random()  # noqa: S311 - fault injection, not security
    client = httpx.AsyncClient(transport=transport, timeout=settings.request_timeout_seconds)
    HTTPXClientInstrumentor().instrument_client(client, tracer_provider=provider)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await client.aclose()
        provider.shutdown()

    app = FastAPI(
        title=f"OpsPilot demo {settings.service_name}",
        version=settings.service_version,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.downstream = Downstream(settings, metrics, client)

    @app.middleware("http")
    async def observe(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        if path in UNFAULTED:
            return await call_next(request)
        route = _route(request)
        start = time.perf_counter()
        span = trace.get_current_span()
        if settings.fault_latency_ms:
            await asyncio.sleep(settings.fault_latency_ms / 1000)
        injected = chance.random() < settings.fault_error_rate
        if injected:
            response: Response = JSONResponse({"detail": "internal error"}, status_code=500)
        else:
            response = await call_next(request)
        elapsed = time.perf_counter() - start
        status = str(response.status_code)
        labels = (settings.service_name, request.method, route, status)
        metrics.requests.labels(*labels).inc()
        metrics.duration.labels(*labels).observe(elapsed)
        level = logging.INFO
        if response.status_code >= 500:
            metrics.errors.labels(settings.service_name, route).inc()
            level = logging.ERROR
            span.set_attribute("error.type", "InjectedFault" if injected else status)
            span.set_status(Status(StatusCode.ERROR, "injected fault" if injected else None))
        logger.log(
            level,
            "request served",
            extra={
                "service": settings.service_name,
                "route": route,
                "method": request.method,
                "status": response.status_code,
                "duration_ms": round(elapsed * 1000, 1),
            },
        )
        return response

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics")
    async def prometheus() -> Response:
        return Response(generate_latest(metrics.registry), media_type=CONTENT_TYPE_LATEST)

    app.include_router(ROUTERS[settings.service_name])

    # Last, so the server span wraps the middleware above and sees its attributes.
    FastAPIInstrumentor.instrument_app(
        app, tracer_provider=provider, excluded_urls="healthz,metrics"
    )
    return app
