"""/v1/favorites, /v1/collections — F13 (API_SPECIFICATION.md §11)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.security import AuthenticatedUser
from app.schemas.collections import (
    CollectionCreateRequest,
    CollectionItemRequest,
    CollectionItemResponse,
    CollectionResponse,
    FavoriteRequest,
    FavoriteResponse,
)
from app.schemas.common import Envelope
from app.services import collections_service

router = APIRouter(tags=["collections"])


@router.post("/favorites", response_model=Envelope[dict], status_code=201)
async def add_favorite(
    body: FavoriteRequest, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[dict]:
    await collections_service.add_favorite(user.id, body.poi_id)
    return Envelope(data={"poi_id": body.poi_id, "favorited": True})


@router.delete("/favorites/{poi_id}", status_code=204)
async def remove_favorite(poi_id: str, user: AuthenticatedUser = Depends(get_current_user)) -> None:
    await collections_service.remove_favorite(user.id, poi_id)


@router.get("/favorites", response_model=Envelope[list[FavoriteResponse]])
async def list_favorites(
    user: AuthenticatedUser = Depends(get_current_user),
) -> Envelope[list[FavoriteResponse]]:
    rows = await collections_service.list_favorites(user.id)
    return Envelope(
        data=[FavoriteResponse.model_validate(dict(r, poi_id=str(r["poi_id"]))) for r in rows]
    )


@router.post("/collections", response_model=Envelope[CollectionResponse], status_code=201)
async def create_collection(
    body: CollectionCreateRequest, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[CollectionResponse]:
    row = await collections_service.create_collection(user.id, body.name)
    row = dict(row, id=str(row["id"]), user_id=str(row["user_id"]))
    return Envelope(data=CollectionResponse.model_validate(row))


@router.get("/collections", response_model=Envelope[list[CollectionResponse]])
async def list_collections(
    user: AuthenticatedUser = Depends(get_current_user),
) -> Envelope[list[CollectionResponse]]:
    rows = await collections_service.list_collections(user.id)
    payload = [dict(r, id=str(r["id"]), user_id=str(r["user_id"])) for r in rows]
    return Envelope(data=[CollectionResponse.model_validate(p) for p in payload])


@router.post(
    "/collections/{collection_id}/items",
    response_model=Envelope[list[CollectionItemResponse]],
    status_code=201,
)
async def add_collection_item(
    collection_id: str,
    body: CollectionItemRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Envelope[list[CollectionItemResponse]]:
    await collections_service.add_item_to_collection(user.id, collection_id, body.poi_id)
    rows = await collections_service.list_collection_items(user.id, collection_id)
    payload = [dict(r, poi_id=str(r["poi_id"])) for r in rows]
    return Envelope(data=[CollectionItemResponse.model_validate(p) for p in payload])


@router.get(
    "/collections/{collection_id}/items", response_model=Envelope[list[CollectionItemResponse]]
)
async def get_collection_items(
    collection_id: str, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[list[CollectionItemResponse]]:
    rows = await collections_service.list_collection_items(user.id, collection_id)
    payload = [dict(r, poi_id=str(r["poi_id"])) for r in rows]
    return Envelope(data=[CollectionItemResponse.model_validate(p) for p in payload])
