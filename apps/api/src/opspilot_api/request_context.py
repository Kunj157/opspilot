import re
import time
import uuid
from contextvars import ContextVar

import structlog
from fastapi import status
from opentelemetry import context as otel_context
from opentelemetry import propagate, trace
from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

logger = structlog.get_logger()

current_request_id: ContextVar[str | None] = ContextVar("current_request_id", default=None)
current_client_ip: ContextVar[str | None] = ContextVar("current_client_ip", default=None)


def _trace_context(scope: Scope) -> tuple[dict[str, str], otel_context.Context | None]:
    """Trace and span IDs for the log context, and a context to attach, if any.

    An active span (OpenTelemetry instrumentation in front of this middleware)
    wins. Otherwise the W3C `traceparent` header is parsed by the configured
    propagator; its span ID is the caller's span, the parent of this request.
    Malformed headers are ignored.
    """
    span_context = trace.get_current_span().get_span_context()
    extracted: otel_context.Context | None = None
    if not span_context.is_valid:
        carrier = {
            name.decode("latin-1").lower(): value.decode("latin-1")
            for name, value in scope.get("headers", [])
        }
        extracted = propagate.extract(carrier)
        span_context = trace.get_current_span(extracted).get_span_context()
        if not span_context.is_valid:
            return {}, None
    ids = {
        "trace_id": trace.format_trace_id(span_context.trace_id),
        "span_id": trace.format_span_id(span_context.span_id),
    }
    return ids, extracted


def _request_id_from(scope: Scope) -> str:
    headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
    for name, value in headers:
        if name.decode("latin-1").lower() == REQUEST_ID_HEADER.lower():
            candidate = value.decode("latin-1")
            if _VALID_REQUEST_ID.fullmatch(candidate):
                return candidate
            break
    return str(uuid.uuid4())


class RequestContextMiddleware:
    """Assigns a request ID, binds it to the log context, and logs each request.

    Implemented as pure ASGI middleware so streaming responses (SSE) are not
    buffered.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _request_id_from(scope)
        structlog.contextvars.clear_contextvars()
        trace_ids, extracted = _trace_context(scope)
        structlog.contextvars.bind_contextvars(request_id=request_id, **trace_ids)
        # Downstream calls (published events) continue the caller's trace.
        otel_token = otel_context.attach(extracted) if extracted is not None else None
        client = scope.get("client")
        request_token = current_request_id.set(request_id)
        ip_token = current_client_ip.set(client[0] if client else None)
        started = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_started = True
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            # Details go to the log, never to the caller: a generic body with
            # the request ID to quote when reporting the failure.
            logger.exception("unhandled error")
            if response_started:
                raise
            await JSONResponse(
                {"detail": "Internal server error", "request_id": request_id},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )(scope, receive, send_with_request_id)
        finally:
            logger.info(
                "request completed",
                method=scope["method"],
                path=scope["path"],
                status_code=status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            structlog.contextvars.clear_contextvars()
            if otel_token is not None:
                otel_context.detach(otel_token)
            current_request_id.reset(request_token)
            current_client_ip.reset(ip_token)
