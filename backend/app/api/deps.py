"""
Shared FastAPI dependencies.

get_current_user() is the ONLY way any route handler learns who is
calling. Every protected endpoint takes `user: AuthenticatedUser =
Depends(get_current_user)` and scopes its queries by `user.id` — never by
a user id read from the path, query string, or request body. This is what
"do not trust a client-supplied user_id when identity can be derived from
authentication" (CLAUDE.md §8) means in code, not just in principle.
"""

from __future__ import annotations

from fastapi import Depends, Header

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import AuthenticatedUser, verify_access_token
from app.repositories.profiles_repository import ProfilesRepository


async def get_bearer_token(authorization: str | None = Header(default=None)) -> str:
    """Extracts the raw bearer token from the Authorization header. Split
    out from get_current_user() so the (rare) call site that needs the raw
    token itself — logout, which forwards it to Supabase Auth's own logout
    endpoint — doesn't have to re-parse the header; FastAPI caches this
    dependency's result per-request, so it only runs once even when both
    get_bearer_token and get_current_user are declared on the same route."""
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("Authentication required.")

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise UnauthorizedError("Authentication required.")

    return token


async def get_current_user(token: str = Depends(get_bearer_token)) -> AuthenticatedUser:
    """Cryptographically verifies the bearer token and returns the
    authenticated identity. Raises 401 on any failure — never partially
    authenticates."""
    return verify_access_token(token)


async def require_admin(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    """Gate for `/v1/admin/*` (F14 review moderation, API_SPECIFICATION.md
    §19). `AuthenticatedUser.role` is the Postgres ROLE CLAIM from the JWT
    (always "authenticated") — application-level admin status lives in
    `profiles.role` instead (DATABASE_SCHEMA.md's own RLS policies check
    exactly this column, e.g. `pois_write_admin`), so this dependency reads
    the real profile row rather than trusting anything client-supplied."""
    profile = await ProfilesRepository().get_by_id(user.id)
    if profile is None or profile.get("role") != "admin":
        raise ForbiddenError("This action requires an administrator role.")
    return user
