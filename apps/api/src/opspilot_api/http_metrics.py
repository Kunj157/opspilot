"""Request metrics for the API, in the same shape as the demo services.

Exposed at /metrics (outside /api/v1; the network policy limits it to the
cluster's Prometheus). The canary analysis compares error rate and p95
latency between releases from these series.
"""

import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

SERVICE = "opspilot-api"
REQUESTS = Counter("http_requests_total", "HTTP requests", ["service", "method", "route", "status"])
ERRORS = Counter("http_errors_total", "HTTP 5xx responses", ["service", "method", "route"])
DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration",
    ["service", "method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


def _route(scope: Scope) -> str:
    """The route template, never the raw path (IDs would explode cardinality)."""
    app = scope.get("app")
    for route in getattr(getattr(app, "router", None), "routes", []):
        match, _ = route.matches(scope)
        if match is Match.FULL:
            return str(getattr(route, "path", "unmatched"))
    return "unmatched"


class MetricsMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] == "/metrics":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status = 500

        async def capture(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            route, method = _route(scope), scope["method"]
            REQUESTS.labels(SERVICE, method, route, str(status)).inc()
            if status >= 500:
                ERRORS.labels(SERVICE, method, route).inc()
            DURATION.labels(SERVICE, method, route).observe(time.perf_counter() - started)


async def metrics(request: Request) -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
