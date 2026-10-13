"""Backstop: every authenticated mutating request leaves an audit record,
even if the route itself records nothing more specific."""

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from opspilot_api.audit.service import record
from opspilot_api.auth.principal import Principal
from opspilot_api.db.session import SessionFactory

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

logger = structlog.get_logger()


class AuditMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in MUTATING_METHODS:
            await self.app(scope, receive, send)
            return

        status_code = 500

        async def capture_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture_status)
        finally:
            principal: Principal | None = scope.get("state", {}).get("principal")
            if principal is not None:
                await self._write(scope, principal, status_code)

    async def _write(self, scope: Scope, principal: Principal, status_code: int) -> None:
        factory: SessionFactory | None = scope["app"].state.session_factory
        if factory is None:
            return
        try:
            async with factory() as session:
                await record(
                    session,
                    principal=principal,
                    action=f"http.{scope['method'].lower()}",
                    resource_type="http_request",
                    resource_id=scope["path"],
                    metadata={"method": scope["method"], "status_code": status_code},
                )
                await session.commit()
        except Exception:
            logger.exception("audit record could not be written", path=scope["path"])
