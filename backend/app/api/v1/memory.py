"""/v1/trips/{id}/memory-items — F11 (API_SPECIFICATION.md §10)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.security import AuthenticatedUser
from app.schemas.common import Envelope
from app.schemas.memory import MemoryItemCreateRequest, MemoryItemResponse
from app.services import memory_service

router = APIRouter(prefix="/trips/{trip_id}/memory-items", tags=["memory-box"])


def _to_response(row: dict) -> dict:
    return dict(row, id=str(row["id"]), trip_id=str(row["trip_id"]), user_id=str(row["user_id"]))


@router.post("", response_model=Envelope[MemoryItemResponse], status_code=201)
async def create_memory_item(
    trip_id: str, body: MemoryItemCreateRequest, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[MemoryItemResponse]:
    row = await memory_service.create_memory_item(
        trip_id,
        user.id,
        body.item_type,
        body.storage_path,
        body.caption,
        body.taken_at.isoformat() if body.taken_at else None,
    )
    return Envelope(data=MemoryItemResponse.model_validate(_to_response(row)))


@router.get("", response_model=Envelope[list[MemoryItemResponse]])
async def list_memory_items(
    trip_id: str,
    limit: int = 30,
    offset: int = 0,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Envelope[list[MemoryItemResponse]]:
    rows = await memory_service.list_memory_items(trip_id, user.id, limit, offset)
    return Envelope(data=[MemoryItemResponse.model_validate(_to_response(r)) for r in rows])


@router.get("/export", response_model=Envelope[list[MemoryItemResponse]])
async def export_memory_items(
    trip_id: str, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[list[MemoryItemResponse]]:
    rows = await memory_service.export_memory_items(trip_id, user.id)
    return Envelope(data=[MemoryItemResponse.model_validate(_to_response(r)) for r in rows])


@router.delete("/{item_id}", status_code=204)
async def delete_memory_item(
    trip_id: str, item_id: str, user: AuthenticatedUser = Depends(get_current_user)
) -> None:
    await memory_service.delete_memory_item(trip_id, item_id, user.id)
