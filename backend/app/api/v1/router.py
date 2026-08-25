"""
Aggregates all /v1 routers into one include-able router.

Health/readiness are intentionally NOT versioned (mounted at root in
app.main) — they are infrastructure probes, not product API surface, and
orchestration platforms conventionally expect them unversioned.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import auth, onboarding, pois

api_v1_router = APIRouter()
api_v1_router.include_router(auth.router)
api_v1_router.include_router(onboarding.router)
api_v1_router.include_router(pois.router)
