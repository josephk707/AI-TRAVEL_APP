"""
Shared response envelope schemas, matching docs/API_SPECIFICATION.md §1.

Success:  { "data": {...}, "meta": {...} }
Error:    { "error": { "code": "...", "message": "...", "details": {...} } }
(the error shape is produced by app.core.exceptions, not this module —
this module defines the *success* envelope + reusable field types.)
"""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Meta(BaseModel):
    next_cursor: str | None = None
    # Set by POST /onboarding/responses (API_SPECIFICATION.md §3) when a save
    # failed and was handed off to a background retry instead of blocking
    # the caller — absent (None) on any endpoint where it doesn't apply.
    saved: bool | None = None


class Envelope(BaseModel, Generic[T]):
    data: T
    meta: Meta | None = None
