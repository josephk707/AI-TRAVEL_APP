"""/v1/safety/*, /v1/trips/{id}/share/*, /v1/share/{token} — F21
(API_SPECIFICATION.md §16)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.core.security import AuthenticatedUser
from app.schemas.common import Envelope
from app.schemas.safety import (
    PublicShareResponse,
    ShareStartResponse,
    SosResponse,
    TrustedContactCreateRequest,
    TrustedContactResponse,
)
from app.services import safety_service

router = APIRouter(tags=["safety"])


class SosRequest(BaseModel):
    trip_id: str | None = None


@router.post("/safety/contacts", response_model=Envelope[TrustedContactResponse], status_code=201)
async def add_trusted_contact(
    body: TrustedContactCreateRequest, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[TrustedContactResponse]:
    row = await safety_service.add_trusted_contact(user.id, body.name, body.phone, body.email)
    return Envelope(
        data=TrustedContactResponse.model_validate(
            dict(row, id=str(row["id"]), user_id=str(row["user_id"]))
        )
    )


@router.get("/safety/contacts", response_model=Envelope[list[TrustedContactResponse]])
async def list_trusted_contacts(
    user: AuthenticatedUser = Depends(get_current_user),
) -> Envelope[list[TrustedContactResponse]]:
    rows = await safety_service.list_trusted_contacts(user.id)
    payload = [dict(r, id=str(r["id"]), user_id=str(r["user_id"])) for r in rows]
    return Envelope(data=[TrustedContactResponse.model_validate(p) for p in payload])


@router.post("/trips/{trip_id}/share/start", response_model=Envelope[ShareStartResponse])
async def start_share(
    trip_id: str, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[ShareStartResponse]:
    row = await safety_service.start_share(trip_id, user.id)
    return Envelope(
        data=ShareStartResponse.model_validate(
            dict(row, id=str(row["id"]), trip_id=str(row["trip_id"]))
        )
    )


@router.post("/trips/{trip_id}/share/stop", status_code=204)
async def stop_share(trip_id: str, user: AuthenticatedUser = Depends(get_current_user)) -> None:
    await safety_service.stop_share(trip_id, user.id)


@router.get("/share/{share_token}", response_model=Envelope[PublicShareResponse])
async def get_public_share(share_token: str) -> Envelope[PublicShareResponse]:
    result = await safety_service.get_public_share(share_token)
    return Envelope(data=PublicShareResponse.model_validate(result))


@router.post("/safety/sos", response_model=Envelope[SosResponse], status_code=201)
async def trigger_sos(
    body: SosRequest, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[SosResponse]:
    row = await safety_service.trigger_sos(user.id, body.trip_id)
    return Envelope(data=SosResponse.model_validate(dict(row, id=str(row["id"]))))
