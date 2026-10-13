import hashlib
import hmac
import json
import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization

from opspilot_api.auth.tokens import InvalidTokenError, TokenVerifier
from tests.support.tokens import AUDIENCE, ISSUER, TokenFactory, new_key


@pytest.fixture
def factory() -> TokenFactory:
    return TokenFactory()


@pytest.fixture
def verifier(factory: TokenFactory) -> TokenVerifier:
    async def resolve(_token: str) -> object:
        return factory.public_key

    return TokenVerifier(issuer=ISSUER, audience=AUDIENCE, key_resolver=resolve)


async def test_accepts_valid_token(verifier: TokenVerifier, factory: TokenFactory) -> None:
    identity = await verifier.verify(factory.token())

    assert identity.subject == "user-sub-1"
    assert identity.issuer == ISSUER
    assert identity.organization == "acme"
    assert identity.email == "cleo@acme.example"
    assert identity.display_name == "Cleo Commander"
    assert identity.roles == frozenset({"incident-commander"})


async def test_ignores_roles_outside_the_application(
    verifier: TokenVerifier, factory: TokenFactory
) -> None:
    token = factory.token(realm_access={"roles": ["uma_authorization", "superuser"]})

    identity = await verifier.verify(token)

    assert identity.roles == frozenset()


async def test_falls_back_to_username_for_display_name(
    verifier: TokenVerifier, factory: TokenFactory
) -> None:
    identity = await verifier.verify(factory.token(name=None, preferred_username="cleo"))

    assert identity.display_name == "cleo"


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"exp": int(time.time()) - 120}, id="expired"),
        pytest.param({"nbf": int(time.time()) + 600}, id="not-yet-valid"),
        pytest.param({"aud": "someone-else"}, id="wrong-audience"),
        pytest.param({"iss": "https://evil.test/realms/opspilot"}, id="wrong-issuer"),
        pytest.param({"sub": None}, id="missing-subject"),
        pytest.param({"exp": None}, id="missing-expiry"),
        pytest.param({"organization": None}, id="missing-organization"),
    ],
)
async def test_rejects_bad_claims(
    verifier: TokenVerifier, factory: TokenFactory, overrides: dict[str, Any]
) -> None:
    with pytest.raises(InvalidTokenError):
        await verifier.verify(factory.token(**overrides))


async def test_rejects_token_signed_by_another_key(
    verifier: TokenVerifier, factory: TokenFactory
) -> None:
    with pytest.raises(InvalidTokenError):
        await verifier.verify(factory.token(key=new_key()))


def _segment(data: dict[str, Any]) -> bytes:
    return jwt.utils.base64url_encode(json.dumps(data).encode())


async def test_rejects_unsigned_token(verifier: TokenVerifier, factory: TokenFactory) -> None:
    token = (
        _segment({"alg": "none", "typ": "JWT"}) + b"." + _segment(factory.claims()) + b"."
    ).decode()

    with pytest.raises(InvalidTokenError):
        await verifier.verify(token)


async def test_rejects_hmac_signed_with_public_key(
    verifier: TokenVerifier, factory: TokenFactory
) -> None:
    # Classic algorithm-confusion attack: HS256 keyed with the RSA public key.
    public_pem = factory.public_key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    signing_input = _segment({"alg": "HS256", "typ": "JWT"}) + b"." + _segment(factory.claims())
    signature = hmac.new(public_pem, signing_input, hashlib.sha256).digest()
    token = (signing_input + b"." + jwt.utils.base64url_encode(signature)).decode()

    with pytest.raises(InvalidTokenError):
        await verifier.verify(token)


@pytest.mark.parametrize("garbage", ["", "not-a-jwt", "a.b.c", "x" * 10_000])
async def test_rejects_garbage(verifier: TokenVerifier, garbage: str) -> None:
    with pytest.raises(InvalidTokenError):
        await verifier.verify(garbage)


async def test_rejects_when_key_cannot_be_resolved(factory: TokenFactory) -> None:
    async def unavailable(_token: str) -> object:
        raise jwt.PyJWKClientError("no matching key")

    verifier = TokenVerifier(issuer=ISSUER, audience=AUDIENCE, key_resolver=unavailable)

    with pytest.raises(InvalidTokenError):
        await verifier.verify(factory.token())
