"""
Aggregates all /v1 routers into one include-able router.

Health/readiness are intentionally NOT versioned (mounted at root in
app.main) — they are infrastructure probes, not product API surface, and
orchestration platforms conventionally expect them unversioned.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    auth,
    budget,
    collections,
    disruptions,
    group,
    heritage,
    location,
    memory,
    notifications,
    offline,
    onboarding,
    phrasebook,
    pois,
    quick_plans,
    reviews,
    safety,
    translation,
    trips,
)

api_v1_router = APIRouter()
api_v1_router.include_router(auth.router)
api_v1_router.include_router(onboarding.router)
api_v1_router.include_router(pois.router)
api_v1_router.include_router(trips.router)
api_v1_router.include_router(translation.router)
api_v1_router.include_router(heritage.router)
api_v1_router.include_router(collections.router)
api_v1_router.include_router(reviews.router)
api_v1_router.include_router(admin.router)
api_v1_router.include_router(budget.router)
api_v1_router.include_router(notifications.router)
api_v1_router.include_router(phrasebook.router)
api_v1_router.include_router(memory.router)
api_v1_router.include_router(location.router)
api_v1_router.include_router(group.router)
api_v1_router.include_router(safety.router)
api_v1_router.include_router(disruptions.router)
api_v1_router.include_router(quick_plans.router)
api_v1_router.include_router(offline.router)
