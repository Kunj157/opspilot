"""Bearer token verification.

Only asymmetric algorithms are accepted, so a token can never be "signed"
with the public key (algorithm confusion) or left unsigned.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import anyio
import httpx
import jwt
import structlog

from opspilot_api.auth.roles import APPLICATION_ROLES

KeyResolver = Callable[[str], Awaitable[Any]]

ALLOWED_ALGORITHMS = ["RS256"]
REQUIRED_CLAIMS = ["exp", "iat", "iss", "aud", "sub"]
MAX_TOKEN_LENGTH = 8192
CLOCK_SKEW_SECONDS = 30

logger = structlog.get_logger()


class InvalidTokenError(Exception):
    """The bearer token cannot be trusted. The message is for logs only."""


class AuthUnavailableError(Exception):
    """The identity provider could not be reached to verify the token."""


@dataclass(frozen=True)
class TokenIdentity:
    issuer: str
    subject: str
    organization: str
    email: str | None
    display_name: str
    roles: frozenset[str]


def discovered_key_resolver(issuer: str) -> KeyResolver:
    """Find the JWKS URL through OIDC discovery on first use, then resolve keys from it."""
    resolver: KeyResolver | None = None
    lock = anyio.Lock()

    async def resolve(token: str) -> Any:
        nonlocal resolver
        if resolver is None:
            async with lock:
                if resolver is None:
                    url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"
                    try:
                        async with httpx.AsyncClient(timeout=5) as client:
                            response = await client.get(url)
                            response.raise_for_status()
                            jwks_uri = response.json()["jwks_uri"]
                    except (httpx.HTTPError, KeyError, ValueError) as exc:
                        raise AuthUnavailableError("OIDC discovery failed") from exc
                    resolver = jwks_key_resolver(jwks_uri)
        return await resolver(token)

    return resolve


def jwks_key_resolver(jwks_url: str) -> KeyResolver:
    """Resolve signing keys from a JWKS endpoint, cached and refreshed on unknown kid."""
    client = jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=300, timeout=5)

    async def resolve(token: str) -> Any:
        signing_key = await anyio.to_thread.run_sync(client.get_signing_key_from_jwt, token)
        return signing_key.key

    return resolve


class TokenVerifier:
    def __init__(self, *, issuer: str, audience: str, key_resolver: KeyResolver) -> None:
        self._issuer = issuer
        self._audience = audience
        self._resolve_key = key_resolver

    async def verify(self, token: str) -> TokenIdentity:
        if not token or len(token) > MAX_TOKEN_LENGTH:
            raise InvalidTokenError("empty or oversized token")
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") not in ALLOWED_ALGORITHMS:
                raise InvalidTokenError(f"algorithm {header.get('alg')!r} not allowed")
            key = await self._resolve_key(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                key,
                algorithms=ALLOWED_ALGORITHMS,
                audience=self._audience,
                issuer=self._issuer,
                leeway=CLOCK_SKEW_SECONDS,
                options={"require": REQUIRED_CLAIMS},
            )
        except (InvalidTokenError, AuthUnavailableError):
            raise
        except jwt.PyJWKClientConnectionError as exc:
            raise AuthUnavailableError("JWKS endpoint unreachable") from exc
        except (jwt.PyJWTError, ValueError) as exc:
            raise InvalidTokenError(type(exc).__name__) from exc

        organization = claims.get("organization")
        if not isinstance(organization, str) or not organization:
            raise InvalidTokenError("missing organization claim")

        token_roles = claims.get("realm_access", {}).get("roles", [])
        return TokenIdentity(
            issuer=claims["iss"],
            subject=claims["sub"],
            organization=organization,
            email=claims.get("email"),
            display_name=claims.get("name") or claims.get("preferred_username") or claims["sub"],
            roles=frozenset(role for role in token_roles if role in APPLICATION_ROLES),
        )
