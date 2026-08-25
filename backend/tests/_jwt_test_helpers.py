"""
Shared helpers for backend JWT unit tests (test_security.py, test_deps.py).

Generates throwaway EC keypairs and a fake JWKS-client stand-in so
app.core.security.verify_access_token() can be unit-tested — real
signature verification, real claim checks — without any network access or
real Supabase credentials. This file does NOT start with `test_`, so
pytest does not collect it as a test module itself (see pyproject.toml's
default `testpaths`/collection pattern).

Trust boundary this deliberately does NOT re-test: PyJWKClient's own
`kid`-matching logic against a real JWKS document. That is third-party,
already-tested library code — FakeJWKSClient below always returns the
configured key regardless of the token's `kid`, so these tests exercise
only THIS project's own verification logic (algorithm allowlisting, claim
checks, error handling), layered on top of a trusted JWKS-lookup result.
"""

from __future__ import annotations

import time
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey
from jwt.algorithms import ECAlgorithm
from jwt.exceptions import PyJWKClientError

TEST_SUPABASE_URL = "https://unit-test-project.supabase.co"
TEST_ISSUER = f"{TEST_SUPABASE_URL}/auth/v1"

# Two distinct keypairs: PRIMARY is "this project's real signing key" for
# test purposes; OTHER simulates a token signed by a DIFFERENT key (e.g. an
# attacker-controlled key, or a rotated-out one) that must be rejected.
PRIMARY_PRIVATE_KEY: EllipticCurvePrivateKey = ec.generate_private_key(ec.SECP256R1())
OTHER_PRIVATE_KEY: EllipticCurvePrivateKey = ec.generate_private_key(ec.SECP256R1())

_EC_ALGORITHM = ECAlgorithm(ECAlgorithm.SHA256)


def make_signing_key(private_key: EllipticCurvePrivateKey = PRIMARY_PRIVATE_KEY) -> jwt.PyJWK:
    """Builds a real jwt.PyJWK (the same type PyJWKClient.get_signing_key_from_jwt
    returns) from a keypair's public half — exactly what verify_access_token
    receives in production, just sourced from a local test key instead of a
    real HTTP fetch."""
    import json

    jwk_dict = json.loads(_EC_ALGORITHM.to_jwk(private_key.public_key()))
    jwk_dict["kid"] = "unit-test-key-1"
    return jwt.PyJWK.from_dict(jwk_dict)


class FakeJWKSClient:
    """Stand-in for jwt.PyJWKClient — always returns the given signing key,
    regardless of the token's own `kid` header."""

    def __init__(self, signing_key: jwt.PyJWK) -> None:
        self._signing_key = signing_key

    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK:
        return self._signing_key


class FailingJWKSClient:
    """Stand-in that simulates a JWKS lookup failure — an unreachable
    endpoint, or no key matching the token's kid (e.g. a rotated-out
    signing key)."""

    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK:
        raise PyJWKClientError("simulated JWKS lookup failure")


def make_token(
    *,
    private_key: EllipticCurvePrivateKey = PRIMARY_PRIVATE_KEY,
    algorithm: str = "ES256",
    sub: str | None = "11111111-1111-4111-8111-111111111111",
    aud: str | None = "authenticated",
    iss: str | None = TEST_ISSUER,
    exp_delta_seconds: float = 3600,
    role: str | None = "authenticated",
    email: str | None = "user@example.com",
    include_exp: bool = True,
    kid: str | None = "unit-test-key-1",
) -> str:
    payload: dict[str, Any] = {}
    if role is not None:
        payload["role"] = role
    if sub is not None:
        payload["sub"] = sub
    if aud is not None:
        payload["aud"] = aud
    if iss is not None:
        payload["iss"] = iss
    if email is not None:
        payload["email"] = email
    if include_exp:
        payload["exp"] = int(time.time() + exp_delta_seconds)
    headers = {"kid": kid} if kid else None
    return jwt.encode(payload, private_key, algorithm=algorithm, headers=headers)
