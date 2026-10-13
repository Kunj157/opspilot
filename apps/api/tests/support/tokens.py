"""Mint test tokens signed with throwaway keys."""

import time
from dataclasses import dataclass, field
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

ISSUER = "https://idp.test/realms/opspilot"
AUDIENCE = "opspilot-api"


def new_key() -> RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@dataclass
class TokenFactory:
    key: RSAPrivateKey = field(default_factory=new_key)
    kid: str = "test-key"

    @property
    def public_key(self) -> RSAPublicKey:
        return self.key.public_key()

    def claims(self, **overrides: Any) -> dict[str, Any]:
        now = int(time.time())
        base: dict[str, Any] = {
            "iss": ISSUER,
            "aud": [AUDIENCE, "account"],
            "sub": "user-sub-1",
            "iat": now,
            "exp": now + 300,
            "email": "cleo@acme.example",
            "name": "Cleo Commander",
            "organization": "acme",
            "realm_access": {"roles": ["incident-commander", "offline_access"]},
        }
        base.update(overrides)
        return {k: v for k, v in base.items() if v is not None}

    def token(self, *, key: RSAPrivateKey | None = None, **overrides: Any) -> str:
        return jwt.encode(
            self.claims(**overrides),
            key or self.key,
            algorithm="RS256",
            headers={"kid": self.kid},
        )
