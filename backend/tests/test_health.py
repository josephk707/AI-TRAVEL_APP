"""Covers CLAUDE.md §10 Phase-1 minimum: app startup, health endpoint,
readiness endpoint."""

from __future__ import annotations

from httpx import AsyncClient


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


async def test_readyz_reports_not_configured_without_database_url(client: AsyncClient) -> None:
    # No DATABASE_URL is set in the test environment (see tests/conftest.py /
    # backend/.env.example) -> readiness must report this honestly, not
    # pretend the database is reachable.
    response = await client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "ready"
    assert body["data"]["checks"]["database"] == "not_configured"


async def test_openapi_docs_available(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"]
