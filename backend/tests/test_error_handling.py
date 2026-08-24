"""
Exercises the real exception-handling machinery in app.core.exceptions
against the standard envelope documented in docs/API_SPECIFICATION.md §1.

Phase 1 ships no business endpoints yet, so a couple of tests attach a
throwaway route to a fresh FastAPI app (using the SAME
register_exception_handlers used by the real app) purely to exercise the
handler behavior end-to-end rather than unit-testing it in isolation.
This throwaway route is never part of the shipped application.
"""

from __future__ import annotations

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import NotFoundError, register_exception_handlers
from app.main import app as real_app


async def test_unknown_route_returns_404_with_standard_envelope() -> None:
    transport = ASGITransport(app=real_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/this-route-does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert "error" in body
    assert body["error"]["code"]
    assert body["error"]["message"]


def _build_probe_app() -> FastAPI:
    """A minimal app wired with the real exception handlers, plus routes
    that deliberately fail in specific ways, for handler-behavior testing."""
    probe_app = FastAPI()
    register_exception_handlers(probe_app)

    @probe_app.get("/probe/validation")
    async def needs_int(value: int) -> dict[str, int]:
        return {"value": value}

    @probe_app.get("/probe/app-error")
    async def raises_app_error() -> None:
        raise NotFoundError("Probe resource not found", details={"id": "abc"})

    @probe_app.get("/probe/unhandled")
    async def raises_unhandled() -> None:
        raise RuntimeError("internal secret detail that must never reach the client")

    return probe_app


async def test_request_validation_error_returns_400_not_422() -> None:
    probe_app = _build_probe_app()
    transport = ASGITransport(app=probe_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/probe/validation", params={"value": "not-an-int"})
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"


async def test_app_error_uses_its_declared_status_and_code() -> None:
    probe_app = _build_probe_app()
    transport = ASGITransport(app=probe_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/probe/app-error")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["details"]["id"] == "abc"


async def test_unhandled_exception_returns_500_without_leaking_internal_detail() -> None:
    probe_app = _build_probe_app()
    # raise_app_exceptions=False: Starlette's ServerErrorMiddleware sends the
    # handled response and then deliberately re-raises the original
    # exception (for server-side log visibility) — the HTTP response itself
    # is already correct at that point. Without this flag, httpx's test
    # transport re-raises into the test instead of letting us inspect the
    # response, which is a test-harness quirk, not an app defect.
    transport = ASGITransport(app=probe_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/probe/unhandled")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "internal secret detail" not in response.text
