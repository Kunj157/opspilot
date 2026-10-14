"""Security headers on every API response, and the CORS policy.

The API serves JSON to the web app's server-side proxy, never pages, so the
policy is as tight as it gets: nothing may be framed, sniffed, or loaded, and
JSON responses are never stored by caches. HSTS is sent only when the request
arrived over HTTPS (directly or as reported by a trusted proxy).

CORS is off unless `CORS_ALLOWED_ORIGINS` names origins explicitly: the
browser talks to the web app on its own origin, which calls the API server to
server.
"""

from fastapi import FastAPI
from starlette.datastructures import MutableHeaders
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from opspilot_api.config import Settings

HSTS = "max-age=63072000; includeSubDomains"
BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
}
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
# The interactive docs load their UI bundle from a CDN; they get frame protection only.
DOCS_PATHS = frozenset({"/docs", "/docs/oauth2-redirect", "/redoc"})
DOCS_CSP = "frame-ancestors 'none'"

CORS_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]
CORS_REQUEST_HEADERS = ["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"]
CORS_EXPOSED_HEADERS = ["X-Request-ID", "Retry-After", "Idempotency-Replayed"]


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def add_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in BASE_HEADERS.items():
                    headers.setdefault(name, value)
                headers.setdefault(
                    "Content-Security-Policy",
                    DOCS_CSP if scope["path"] in DOCS_PATHS else API_CSP,
                )
                if scope.get("scheme") == "https":
                    headers.setdefault("Strict-Transport-Security", HSTS)
                if headers.get("content-type", "").startswith("application/json"):
                    headers.setdefault("Cache-Control", "no-store")
            await send(message)

        await self.app(scope, receive, add_headers)


def add_cors(app: FastAPI, settings: Settings) -> None:
    origins = settings.cors_origins
    if not origins:
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_methods=CORS_METHODS,
        allow_headers=CORS_REQUEST_HEADERS,
        expose_headers=CORS_EXPOSED_HEADERS,
        allow_credentials=False,
        max_age=600,
    )
