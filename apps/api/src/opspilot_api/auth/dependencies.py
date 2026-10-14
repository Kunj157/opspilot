from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.auth.principal import Principal
from opspilot_api.auth.provisioning import AccessDeniedError, provision
from opspilot_api.auth.tokens import AuthUnavailableError, InvalidTokenError, TokenVerifier
from opspilot_api.db.session import get_session
from opspilot_api.rate_limit import (
    Policy,
    client_ip,
    enforce_principal_limit,
    get_rate_limiter,
    too_many_requests,
)

logger = structlog.get_logger()
bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(error: str | None = None) -> HTTPException:
    challenge = f'Bearer error="{error}"' if error else "Bearer"
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": challenge}
    )


def get_token_verifier(request: Request) -> TokenVerifier:
    verifier: TokenVerifier | None = request.app.state.token_verifier
    if verifier is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "authentication not configured")
    return verifier


async def get_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Principal:
    if credentials is None:
        raise _unauthorized()
    limiter = get_rate_limiter(request)
    if limiter is not None:
        # An IP that keeps sending bad tokens is refused before verification.
        blocked = await limiter.exhausted(Policy.AUTH_FAILURE, client_ip(request))
        if not blocked.allowed:
            raise too_many_requests(blocked)
    try:
        identity = await verifier.verify(credentials.credentials)
    except InvalidTokenError as exc:
        logger.info("token rejected", reason=str(exc))
        if limiter is not None:
            decision = await limiter.hit(Policy.AUTH_FAILURE, client_ip(request))
            if not decision.allowed:
                raise too_many_requests(decision) from exc
        raise _unauthorized("invalid_token") from exc
    except AuthUnavailableError as exc:
        logger.error("identity provider unavailable", reason=str(exc))
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "authentication unavailable"
        ) from exc

    try:
        principal = await provision(session, identity)
    except AccessDeniedError as exc:
        logger.warning("access denied", reason=str(exc), subject=identity.subject)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden") from exc

    structlog.contextvars.bind_contextvars(
        user_id=str(principal.user_id), organization_id=str(principal.organization_id)
    )
    request.state.principal = principal
    await enforce_principal_limit(request, str(principal.user_id))
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]
