"""/v1/heritage/* — F8 Heritage Narration RAG + F9 Visual Q&A
(API_SPECIFICATION.md §7/§8)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, UploadFile

from app.api.deps import get_current_user
from app.core.rate_limit import ai_rate_limit
from app.core.security import AuthenticatedUser
from app.schemas.common import Envelope
from app.schemas.heritage import NarrationQuery, NarrationResponse, PhotoQaResponse
from app.services import narration_service, photo_qa_service

router = APIRouter(prefix="/heritage", tags=["heritage"])


@router.get("/{poi_id}/narration", response_model=Envelope[NarrationResponse])
async def get_narration(
    poi_id: str,
    params: NarrationQuery = Depends(),
    user: AuthenticatedUser = Depends(get_current_user),
) -> Envelope[NarrationResponse]:
    result = await narration_service.get_narration(poi_id, params.layer, params.section, user.id)
    return Envelope(data=NarrationResponse.model_validate(result))


@router.post("/{poi_id}/photo-qa", response_model=Envelope[PhotoQaResponse])
async def photo_qa(
    poi_id: str,
    image: UploadFile,
    question: str = Form(..., min_length=1, max_length=500),
    user: AuthenticatedUser = Depends(get_current_user),
    _rl: None = Depends(ai_rate_limit),
) -> Envelope[PhotoQaResponse]:
    image_bytes = await image.read()
    result = await photo_qa_service.answer_photo_question(
        poi_id, question, image_bytes, image.content_type or "application/octet-stream", user.id
    )
    return Envelope(data=PhotoQaResponse.model_validate(result))
