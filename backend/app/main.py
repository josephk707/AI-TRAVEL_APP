"""
FastAPI application entry point.

Mounts the unversioned health/readiness probes and the versioned /v1
product API surface (currently /v1/auth/* — see app/api/v1/router.py).
Business-feature endpoints beyond auth are still deferred to later phases
per the approved sequence in CLAUDE.md / IMPLEMENTATION_BLUEPRINT.md.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.health import router as health_router
from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.exceptions import NotFoundError, register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.db.session import close_pool, create_pool

settings = get_settings()
configure_logging()
logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "app_startup",
        extra={"environment": settings.environment, "version": settings.app_version},
    )
    # A missing/unreachable database must never prevent the API process
    # itself from starting — create_pool() returns None rather than
    # raising if DATABASE_URL is unset or unreachable (see app/db/session.py).
    await create_pool()
    yield
    await close_pool()
    logger.info("app_shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "AI Personalized Tourist Guide & Travel Companion (TC-SO1) — "
            "backend API. See docs/API_SPECIFICATION.md for the full contract."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    # Health/readiness: unversioned, root-level infrastructure probes.
    app.include_router(health_router)

    # Versioned product API surface — empty in Phase 1, populated from
    # Phase 3 (Auth) onward per API_SPECIFICATION.md.
    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)

    # Starlette's router returns its own raw 404 ({"detail": "Not Found"})
    # for genuinely unmatched paths WITHOUT raising an exception, so it
    # never reaches register_exception_handlers above. This catch-all
    # (registered last, so it never shadows a real route) routes every
    # unmatched path through our standard error envelope instead.
    @app.api_route(
        "/{full_path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        include_in_schema=False,
    )
    async def catch_all_unmatched(full_path: str) -> None:
        raise NotFoundError(f"No route matches /{full_path}")

    return app


app = create_app()
