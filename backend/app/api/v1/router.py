"""
Aggregates all /v1 routers into one include-able router.

Phase 1: empty (no business endpoints exist yet). Later phases register
their routers here, e.g.:

    from app.api.v1 import trips
    api_v1_router.include_router(trips.router, prefix="/trips", tags=["trips"])

Health/readiness are intentionally NOT versioned (mounted at root in
app.main) — they are infrastructure probes, not product API surface, and
orchestration platforms conventionally expect them unversioned.
"""

from __future__ import annotations

from fastapi import APIRouter

api_v1_router = APIRouter()
