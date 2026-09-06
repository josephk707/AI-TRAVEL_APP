"""
Business logic for /v1/auth/* — route handlers (app/api/v1/auth.py) stay
thin and delegate here, per CLAUDE.md §7 (Router -> Service -> Repository).
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings
from app.core.exceptions import NotFoundError, UpstreamUnavailableError
from app.core.security import AuthenticatedUser
from app.repositories.profiles_repository import ProfilesRepository

logger = logging.getLogger("app.services.auth")


async def bootstrap_session(user: AuthenticatedUser) -> tuple[dict[str, object], bool]:
    """Idempotent "load, or defensively create" — see
    ProfilesRepository.create_if_missing for why the create path is a
    fallback rather than the normal path. Returns (profile, created)."""
    repo = ProfilesRepository()
    existing = await repo.get_by_id(user.id)
    if existing is not None:
        return existing, False

    logger.warning(
        "profile_bootstrap_defensive_create",
        extra={"reason": "trigger_created_row_not_found"},
    )
    created_profile = await repo.create_if_missing(user.id)
    return created_profile, True


async def get_profile(user: AuthenticatedUser) -> dict[str, object]:
    repo = ProfilesRepository()
    profile = await repo.get_by_id(user.id)
    if profile is None:
        # A verified token for a user with no profile row at all indicates
        # a real data-integrity problem (the trigger should guarantee this
        # never happens) — surfaced honestly as 404, not silently
        # fabricated.
        raise NotFoundError("Profile not found for the authenticated user.")
    return profile


async def update_preferred_language(
    user: AuthenticatedUser, preferred_language: str
) -> dict[str, object]:
    """Persists the caller's own UI-language preference. Identity comes
    from the verified token (`user.id`), never a client-supplied id —
    same trust boundary as every other method in this module."""
    repo = ProfilesRepository()
    existing = await repo.get_by_id(user.id)
    if existing is None:
        raise NotFoundError("Profile not found for the authenticated user.")
    return await repo.update_preferred_language(user.id, preferred_language)


async def revoke_session(access_token: str) -> None:
    """Revokes the CALLER'S OWN session via Supabase Auth's own logout
    endpoint, using the caller's own access token — not the service-role
    key. This needs no elevated privilege: GoTrue scopes the revocation to
    whichever session the presented token belongs to. Deliberately never
    escalates to service-role for a user-triggered action like this.

    A failure to reach the upstream auth provider does not fail the whole
    logout: the mobile client discards its local session unconditionally
    either way, and server-side revocation here is defense-in-depth (it
    stops the token being reused if some future business-logic bug
    forgets to check expiry), not the sole protection.
    """
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise UpstreamUnavailableError("Authentication provider is not configured.")

    url = f"{settings.supabase_url}/auth/v1/logout"
    headers = {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {access_token}",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=headers)
        if response.status_code not in (200, 204):
            logger.warning("logout_upstream_rejected", extra={"status": response.status_code})
    except httpx.HTTPError as exc:
        logger.warning("logout_upstream_unreachable", extra={"error_type": type(exc).__name__})
