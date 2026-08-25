"""
JWT verification for Supabase-issued access tokens.

Real cryptographic verification (HS256, using the project's JWT signing
secret) — a token is NEVER decoded without signature verification, and
verification is NEVER disabled "to make development easier" (CLAUDE.md
governance §9 explicitly forbids this, and this phase's own instructions
repeat it). This module is the single source of authenticated identity for
the entire backend; no endpoint accepts a user id from the client instead
of deriving it here.

SECRET SAFETY: the JWT secret itself is the single most sensitive value in
the system (anyone holding it can forge a valid session for any user) — it
is a SecretStr (app/core/config.py) and unwrapped via .get_secret_value()
only at the point PyJWT needs it, never logged. Verification failures are
logged by exception TYPE only, never the token or the raw exception
message (which can echo back parts of the rejected payload).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWTError

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError

logger = logging.getLogger("app.security")

SUPABASE_JWT_AUDIENCE = "authenticated"
SUPABASE_JWT_ALGORITHM = "HS256"


@dataclass(frozen=True)
class AuthenticatedUser:
    """The verified identity of the caller — everything a request handler
    is allowed to know about "who is this" comes from here, never from a
    client-supplied parameter."""

    id: str  # uuid string, from the JWT `sub` claim
    email: str | None
    role: str  # e.g. "authenticated" (Supabase's Postgres role claim)


def verify_access_token(token: str) -> AuthenticatedUser:
    """Cryptographically verifies a Supabase access token and returns the
    authenticated identity.

    Raises UnauthorizedError (never a raw PyJWTError) on ANY failure:
    expired, malformed, bad signature, wrong audience, wrong issuer,
    missing required claims. Fails CLOSED if the server itself isn't fully
    configured (JWT secret or project URL missing) — never falls back to
    "trust it anyway."

    Issuer is checked in addition to signature/audience/expiry: the
    signature alone already proves the token was signed with THIS
    project's secret, but pinning `iss` to this exact project's Auth URL
    is the standard, cheap defense-in-depth check this phase's spec calls
    for explicitly, and costs nothing once the secret is already known.
    """
    settings = get_settings()
    if settings.supabase_jwt_secret is None or not settings.supabase_url:
        logger.error("jwt_verification_not_configured")
        raise UnauthorizedError("Authentication is not configured on this server.")

    secret = settings.supabase_jwt_secret.get_secret_value()
    expected_issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1"

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            secret,
            algorithms=[SUPABASE_JWT_ALGORITHM],
            audience=SUPABASE_JWT_AUDIENCE,
            issuer=expected_issuer,
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
