"""
JWT verification for Supabase-issued access tokens.

Real cryptographic verification via Supabase's public JWKS endpoint
(asymmetric — Supabase's "JWT Signing Keys" system) — a token is NEVER
decoded without signature verification, and verification is NEVER disabled
"to make development easier" (CLAUDE.md governance §9 explicitly forbids
this, and this phase's own instructions repeat it). This module is the
single source of authenticated identity for the entire backend; no
endpoint accepts a user id from the client instead of deriving it here.

ARCHITECTURE DECISION (documented per CLAUDE.md §13 — this is a deviation
from this module's original design, not a silent change): this module
previously verified tokens using a shared HS256 secret
(`SUPABASE_JWT_SECRET`). During Phase 3 certification, decoding a REAL
access token's header from this project's live Supabase instance (no
secret required to read a JWT header — it is not encrypted, only signed)
showed `"alg": "ES256"`, and the project's public JWKS endpoint
(`{SUPABASE_URL}/auth/v1/.well-known/jwks.json`) serves a matching EC
public key. This project uses Supabase's newer asymmetric "JWT Signing
Keys" feature, not the legacy shared-secret HS256 model — a shared secret
can never verify an asymmetrically-signed token, so the previous
implementation could not have worked here regardless of what secret value
was supplied. See docs/AUTHENTICATION_SETUP.md §7 for the full writeup.

JWKS verification needs no secret at all: `PyJWKClient` fetches the
project's public signing key(s) from the JWKS endpoint above (public, no
auth required, nothing sensitive in its response), matches the token's
`kid` header to the correct public key, and PyJWT verifies the signature
against that key. The algorithm actually used for verification comes from
the matched key's own JWK metadata (`kty`/`crv`, e.g. an EC P-256 key
implies ES256) — never from the token's own header, which an attacker
controls — so this remains immune to algorithm-confusion attacks.
ALLOWED_JWT_ALGORITHMS further restricts accepted keys to the asymmetric
algorithms Supabase's signing-keys feature actually issues; a symmetric
("oct"/HS256) key is never accepted here even if one somehow appeared in a
JWKS response, since HS256 verification uses the same value to sign and
verify and would defeat the entire point of asymmetric verification.

SECRET SAFETY: nothing in this module is a secret — the JWKS response and
the public keys derived from it are, by definition, public. Verification
failures are still logged by exception TYPE only, never the token or the
raw exception message (which can echo back parts of the rejected
payload), consistent with the rest of this project's logging discipline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError

logger = logging.getLogger("app.security")

SUPABASE_JWT_AUDIENCE = "authenticated"

# Supabase's "JWT Signing Keys" feature issues only asymmetric keys (RSA or
# Elliptic Curve) — never a symmetric/HS256 key. Pinning this allowlist
# means a malformed or unexpected JWKS response could never cause a
# fall-back to a symmetric algorithm (the classic algorithm-confusion
# attack against an asymmetric-key verifier).
ALLOWED_JWT_ALGORITHMS = frozenset({"ES256", "RS256"})

# Tolerates small clock drift between this server and Supabase's own
# servers when checking `iat`/`exp`/`nbf`. Found necessary empirically
# during Phase 3 certification: with PyJWT's default zero leeway, a
# genuine, correctly-signed token from this project intermittently failed
# verification with ImmatureSignatureError ("The token is not yet valid
# (iat)") even though the two servers' clocks were, by direct measurement,
# only ~1-2 seconds apart — well within normal NTP-synced drift. Tolerating
# a small, fixed window is the standard, universally-recommended mitigation
# for this exact class of distributed-clock issue (every major JWT library
# supports a leeway parameter for precisely this reason); it does not
# meaningfully weaken expiry enforcement — a token's effective lifetime
# changes by at most this many seconds at either edge, not indefinitely.
CLOCK_SKEW_LEEWAY_SECONDS = 10


@dataclass(frozen=True)
class AuthenticatedUser:
    """The verified identity of the caller — everything a request handler
    is allowed to know about "who is this" comes from here, never from a
    client-supplied parameter."""

    id: str  # uuid string, from the JWT `sub` claim
    email: str | None
    role: str  # e.g. "authenticated" (Supabase's Postgres role claim)


@lru_cache
def _get_jwks_client(jwks_url: str) -> PyJWKClient:
    """One cached client per JWKS URL for the process lifetime. PyJWKClient
    itself caches the fetched key set in memory (default `lifespan=300`
    seconds) and transparently re-fetches on a cache miss — e.g. after
    Supabase rotates its signing key and a token references a `kid` this
    process hasn't seen yet — so this is not a stale-forever cache.
    `cache_keys=True` additionally caches resolved individual `PyJWK`
    objects by kid, avoiding re-parsing the same key on every request."""
    return PyJWKClient(jwks_url, cache_keys=True)


def verify_access_token(token: str) -> AuthenticatedUser:
    """Cryptographically verifies a Supabase access token (via JWKS) and
    returns the authenticated identity.

    Raises UnauthorizedError (never a raw PyJWT/PyJWKClient error) on ANY
    failure: expired, malformed, bad signature, wrong audience, wrong
    issuer, missing required claims, unreachable/misconfigured JWKS
    endpoint, or a key algorithm outside ALLOWED_JWT_ALGORITHMS. Fails
    CLOSED if the server itself isn't fully configured (no project URL) —
    never falls back to "trust it anyway."

    Issuer is checked in addition to signature/audience/expiry: the
    signature alone already proves the token was signed by THIS project's
    own key, but pinning `iss` to this exact project's Auth URL is a
    cheap, standard defense-in-depth check that costs nothing once the
    signing key is already resolved.
    """
    settings = get_settings()
    if not settings.supabase_url:
        logger.error("jwt_verification_not_configured")
        raise UnauthorizedError("Authentication is not configured on this server.")

    base_url = settings.supabase_url.rstrip("/")
    expected_issuer = f"{base_url}/auth/v1"
    jwks_url = f"{base_url}/auth/v1/.well-known/jwks.json"

    try:
        signing_key = _get_jwks_client(jwks_url).get_signing_key_from_jwt(token)
    except PyJWTError as exc:
        # PyJWTError (not just its PyJWKClientError subclass) because
        # get_signing_key_from_jwt() first decodes the token's header
        # WITHOUT going through PyJWKClient's own error wrapping at all —
        # a syntactically malformed token (too few "." segments, invalid
        # base64, etc.) raises a raw jwt.exceptions.DecodeError directly
        # from that header-parsing step, before PyJWKClientError's kid-
        # lookup logic is ever reached. Catching only PyJWKClientError here
        # left malformed tokens as an unhandled exception (a real bug found
        # during Phase 3 certification, not a hypothetical one). This
        # branch now covers both: an unreachable JWKS endpoint, no key
        # matching the token's kid (e.g. a rotated-out signing key), AND a
        # token too malformed to even read a kid from.
        logger.info("jwt_jwks_lookup_failed", extra={"error_type": type(exc).__name__})
        raise UnauthorizedError("Invalid or expired authentication token.") from exc

    if signing_key.algorithm_name not in ALLOWED_JWT_ALGORITHMS:
        logger.error(
            "jwt_verification_rejected_algorithm",
            extra={"algorithm": signing_key.algorithm_name},
        )
        raise UnauthorizedError("Invalid or expired authentication token.")

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=[signing_key.algorithm_name],
            audience=SUPABASE_JWT_AUDIENCE,
            issuer=expected_issuer,
            leeway=CLOCK_SKEW_LEEWAY_SECONDS,
            options={"require": ["exp", "sub", "aud", "iss"]},
        )
    except PyJWTError as exc:
        logger.info("jwt_verification_failed", extra={"error_type": type(exc).__name__})
        raise UnauthorizedError("Invalid or expired authentication token.") from exc

    subject = payload.get("sub")
    if not subject:
        logger.info("jwt_verification_failed", extra={"error_type": "MissingSubjectClaim"})
        raise UnauthorizedError("Invalid or expired authentication token.")

    return AuthenticatedUser(
        id=str(subject),
        email=payload.get("email"),
        role=str(payload.get("role", "authenticated")),
    )
