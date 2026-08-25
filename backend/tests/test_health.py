"""Covers CLAUDE.md §10 Phase-1 minimum: app startup, health endpoint,
readiness endpoint."""

from __future__ import annotations

from httpx import AsyncClient

from app.core.config import get_settings


async def test_app_starts_and_root_health_responds(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "ok"
    assert "app_version" in body["data"]


async def test_healthz_envelope_shape_matches_api_spec(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    body = response.json()
    assert "data" in body
    assert "error" not in body


async def test_readyz_reflects_actual_database_configuration(client: AsyncClient) -> None:
    # Deliberately adaptive rather than hardcoding "not_configured": this
    # test suite may run in a dev environment where backend/.env genuinely
    # has a real DATABASE_URL configured (Phase 2 onward) or one where it
    # doesn't (a fresh Phase-1-only checkout) — both are valid, and
    # readiness must honestly reflect whichever is actually true, never a
    # hardcoded assumption about the environment it happens to run in.
    #
    # The ground truth for "is a database configured" is what the app's own
    # Settings object resolved (get_settings(), which loads backend/.env
    # via pydantic-settings) — NOT os.environ directly. Settings reads
    # backend/.env regardless of whether the value is also exported into
    # the shell's environment, so checking os.environ here previously
    # produced a false failure any time a real backend/.env existed but the
    # shell running pytest hadn't separately exported DATABASE_URL (the
    # normal case for a plain `pytest` invocation, as opposed to
    # scripts/run_live_tests.py, which does export it).
    response = await client.get("/readyz")
    body = response.json()
    checks = body["data"]["checks"]

    if get_settings().database_url is not None:
        assert response.status_code in (200, 503)
        assert checks["database"] in ("ok", "error")
        assert checks["schema_status"] in ("ok", "error")
    else:
        assert response.status_code == 200
        assert body["data"]["status"] == "ready"
        assert checks["database"] == "not_configured"
        assert checks["schema_status"] == "not_configured"


async def test_openapi_docs_available(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"]
