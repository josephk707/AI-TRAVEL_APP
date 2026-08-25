"""
Unit tests for app/api/deps.py — header parsing / token extraction only.
Cryptographic verification itself is covered by tests/test_security.py;
these tests call the dependency functions directly (they're plain async
functions FastAPI happens to inject) with a test-only EC keypair and a
faked JWKS lookup (tests/_jwt_test_helpers.py), so no real credentials or
network access are needed.
"""

from __future__ import annotations

import pytest

from app.api.deps import get_bearer_token, get_current_user
from app.core.config import Settings
from app.core.exceptions import UnauthorizedError
from tests._jwt_test_helpers import TEST_SUPABASE_URL, FakeJWKSClient, make_signing_key, make_token


@pytest.mark.parametrize("header_value", [None, "", "NotBearer abc123", "Bearer", "Bearer   "])
async def test_get_bearer_token_rejects_missing_or_malformed_header(
    header_value: str | None,
) -> None:
    with pytest.raises(UnauthorizedError):
        await get_bearer_token(authorization=header_value)


async def test_get_bearer_token_extracts_the_token_from_a_well_formed_header() -> None:
    token = await get_bearer_token(authorization="Bearer some.jwt.token")
    assert token == "some.jwt.token"


async def test_get_current_user_delegates_to_real_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.security.get_settings",
        lambda: Settings(_env_file=None, supabase_url=TEST_SUPABASE_URL),
    )
    monkeypatch.setattr(
        "app.core.security._get_jwks_client", lambda url: FakeJWKSClient(make_signing_key())
    )
    token = make_token(sub="33333333-3333-4333-8333-333333333333")

    user = await get_current_user(token=token)

    assert user.id == "33333333-3333-4333-8333-333333333333"


async def test_get_current_user_rejects_an_invalid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.security.get_settings",
        lambda: Settings(_env_file=None, supabase_url=TEST_SUPABASE_URL),
    )
    monkeypatch.setattr(
        "app.core.security._get_jwks_client", lambda url: FakeJWKSClient(make_signing_key())
    )

    with pytest.raises(UnauthorizedError):
        await get_current_user(token="garbage-not-a-jwt")
