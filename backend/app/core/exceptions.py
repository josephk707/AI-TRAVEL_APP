"""
Standard error model + exception handlers.

Every error response — regardless of source (a raised AppError, an
unhandled HTTPException, a request-validation failure, or a truly
unexpected exception) — is normalized into the single envelope shape
documented in docs/API_SPECIFICATION.md §1:

    { "error": { "code": "...", "message": "...", "details": {...} } }

HTTP status codes follow the same document's table:
    400 validation error (malformed input)
    401 missing/invalid/expired auth
    403 authenticated but not authorized
    404 not found / not visible to this user
    409 conflict
    422 business-rule violation
    429 rate limit exceeded
    502/503 upstream dependency unavailable

Unhandled exceptions are NEVER leaked to the client (no stack trace, no
internal message) — they are logged server-side with full detail and the
client receives a generic 500 envelope. This is what "never silently
swallow errors" (CLAUDE.md §9) means in practice: swallow nothing from the
logs, leak nothing to the client.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError

logger = logging.getLogger("app.errors")


class AppError(Exception):
    """Base application error — raise this from services, not raw HTTPException,
    so every business-logic error carries a stable machine-readable `code`."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found", details: dict[str, Any] | None = None):
        super().__init__("NOT_FOUND", message, status.HTTP_404_NOT_FOUND, details)


class UnauthorizedError(AppError):
    def __init__(
        self, message: str = "Authentication required", details: dict[str, Any] | None = None
    ):
        super().__init__("UNAUTHORIZED", message, status.HTTP_401_UNAUTHORIZED, details)


class ForbiddenError(AppError):
    def __init__(
        self,
        message: str = "Not authorized for this resource",
        details: dict[str, Any] | None = None,
    ):
        super().__init__("FORBIDDEN", message, status.HTTP_403_FORBIDDEN, details)


class ConflictError(AppError):
    def __init__(self, message: str = "Conflict", details: dict[str, Any] | None = None):
        super().__init__("CONFLICT", message, status.HTTP_409_CONFLICT, details)


class BusinessRuleError(AppError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(code, message, status.HTTP_422_UNPROCESSABLE_ENTITY, details)


class UpstreamUnavailableError(AppError):
    def __init__(
        self,
        message: str = "An upstream service is unavailable",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            "UPSTREAM_UNAVAILABLE", message, status.HTTP_503_SERVICE_UNAVAILABLE, details
        )


def _error_envelope(
    code: str, message: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def _json_safe_pydantic_errors(errors: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """pydantic's `.errors()` embeds the raw exception instance under
    `ctx.error` for a validator that raises ValueError/AssertionError (e.g.
    TranslateTextRequest's two-sentence limit) — not JSON serializable by
    plain `json.dumps`/starlette's JSONResponse. `msg` already carries the
    human-readable text, so `ctx` is stringified rather than dropped
    (keeps any other, genuinely serializable context)."""
    safe: list[dict[str, Any]] = []
    for error in errors:
        error = dict(error)
        ctx = error.get("ctx")
        if isinstance(ctx, dict):
            error["ctx"] = {k: str(v) if isinstance(v, Exception) else v for k, v in ctx.items()}
        safe.append(error)
    return safe


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.warning("app_error", extra={"code": exc.code, "path": request.url.path})
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_envelope(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Malformed input -> 400 per API_SPECIFICATION.md §1, NOT FastAPI's
        # default 422 (422 is reserved here for business-rule violations).
        # exc.errors() can embed a raw, non-JSON-serializable ValueError in
        # ctx.error for a field_validator that raises (e.g.
        # TranslateTextRequest's two-sentence limit) — found as a real bug
        # by this phase's own live test before it was ever a hypothetical.
        logger.info("validation_error", extra={"path": request.url.path})
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=_error_envelope(
                "VALIDATION_ERROR",
                "Request input failed validation.",
                {"errors": _json_safe_pydantic_errors(exc.errors())},
            ),
        )

    @app.exception_handler(PydanticValidationError)
    async def handle_pydantic_validation_error(
        request: Request, exc: PydanticValidationError
    ) -> JSONResponse:
        # A model_validator's cross-field check (e.g. PoiSearchQuery's
        # "query or lat/lng required", app/schemas/poi.py) raises inside a
        # Depends()-injected pydantic model's own __init__ during FastAPI's
        # dependency resolution — a different code path from a request
        # BODY failing validation (which FastAPI itself converts to
        # RequestValidationError automatically). Without this handler such
        # an error would otherwise be an unhandled 500, found as a real bug
        # by this project's own live API tests (F6, tests/test_pois_api.py)
        # rather than assumed away. Normalized to the same 400 envelope as
        # every other validation failure, per API_SPECIFICATION.md §1.
        logger.info("pydantic_validation_error", extra={"path": request.url.path})
        # exc.errors() can embed a raw, non-JSON-serializable exception
        # object in ctx.error for a model_validator failure — exc.json()
        # (then re-parsed) is pydantic's own guaranteed-serializable
        # rendering of the same error list.
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=_error_envelope(
                "VALIDATION_ERROR",
                "Request input failed validation.",
                {"errors": json.loads(exc.json())},
            ),
        )

    @app.exception_handler(FastAPIHTTPException)
    async def handle_http_exception(request: Request, exc: FastAPIHTTPException) -> JSONResponse:
        logger.info("http_exception", extra={"status": exc.status_code, "path": request.url.path})
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_envelope("HTTP_ERROR", str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Full detail logged server-side; nothing internal leaked to the client.
        logger.exception("unhandled_exception", extra={"path": request.url.path})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_envelope(
                "INTERNAL_ERROR",
                "An unexpected error occurred. This has been logged.",
            ),
        )
