"""
/v1/auth/* — see docs/API_SPECIFICATION.md §2 for the full contract.

Every route here requires a real, cryptographically verified Supabase
access token (via app.api.deps.get_current_user) — there is no
unauthenticated path in this router, and no route accepts a user id as
input; identity always comes from the verified token.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_bearer_token, get_current_user
from app.core.security import AuthenticatedUser
from app.schemas.auth import (
    BootstrapResponse,
    LogoutResponse,
    ProfileResponse,
    UpdateProfileRequest,
)
from app.schemas.common import Envelope
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/session/bootstrap", response_model=Envelope[BootstrapResponse])
async def session_bootstrap(
    user: AuthenticatedUser = Depends(get_current_user),
) -> Envelope[BootstrapResponse]:
    """Idempotent load-or-defensive-create, called once right after the
    mobile client obtains a session (post-OAuth). Normally a no-op load —
    see auth_service.bootstrap_session."""
    profile, created = await auth_service.bootstrap_session(user)
    return Envelope(
        data=BootstrapResponse(profile=ProfileResponse.model_validate(profile), created=created)
    )


@router.get("/me", response_model=Envelope[ProfileResponse])
async def get_me(user: AuthenticatedUser = Depends(get_current_user)) -> Envelope[ProfileResponse]:
    """The minimal real protected endpoint this phase requires: proves the
    full chain (mobile token -> FastAPI verification -> Postgres) end to
    end by returning the caller's own profile, scoped by the verified
    token's subject — never by a client-supplied id."""
    profile = await auth_service.get_profile(user)
    return Envelope(data=ProfileResponse.model_validate(profile))


@router.patch("/me", response_model=Envelope[ProfileResponse])
async def update_me(
    body: UpdateProfileRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Envelope[ProfileResponse]:
    """Language-settings phase — the mobile Language Settings screen calls
    this to persist the caller's UI-language preference server-side (so it
    survives reinstall/new-device login, not just this device's local
    storage). Scoped to `preferred_language` only, see UpdateProfileRequest."""
    profile = await auth_service.update_preferred_language(user, body.preferred_language)
    return Envelope(data=ProfileResponse.model_validate(profile))


@router.post("/logout", response_model=Envelope[LogoutResponse])
async def logout(
    token: str = Depends(get_bearer_token),
    user: AuthenticatedUser = Depends(get_current_user),
) -> Envelope[LogoutResponse]:
    """Requires a currently-valid token (via get_current_user) so an
    already-expired/garbage token can't be used to probe this endpoint;
    revokes that session's refresh token server-side, then the response
    tells the client it is safe to discard its local session regardless of
    upstream outcome (see auth_service.revoke_session)."""
    del user  # identity not needed beyond proving the token was valid
    await auth_service.revoke_session(token)
    return Envelope(data=LogoutResponse(status="logged_out"))
