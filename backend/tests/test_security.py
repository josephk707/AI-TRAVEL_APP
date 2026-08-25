"""
Unit tests for app/core/security.py's verify_access_token() — real
cryptographic JWT verification logic, exercised with a TEST-ONLY signing
secret minted in-process (never the real SUPABASE_JWT_SECRET, never a
token obtained from the live Supabase project). This is deliberately
"UNIT", not "INTEGRATION", per this phase's testing taxonomy: it proves
the verification LOGIC is correct (signature, expiry, audience, issuer,
required claims) without needing any real credentials or network access —
real Supabase-issued tokens are exercised separately in
tests/test_auth_api.py (integration).
"""

from __future__ import annotations

import time

import jwt
import pytest

from app.core.config import Settings
from app.core.exceptions import UnauthorizedError
from app.core.security import verify_access_token

TEST_SECRET = "unit-test-only-signing-secret-not-a-real-supabase-secret-32bytes+"
TEST_SUPABASE_URL = "https://unit-test-project.supabase.co"
TEST_ISSUER = f"{TEST_SUPABASE_URL}/auth/v1"


def _settings(
    secret: str | None = TEST_SECRET, supabase_url: str | None = TEST_SUPABASE_URL
) -> Settings:
    return Settings(_env_file=None, supabase_jwt_secret=secret, supabase_url=supabase_url)


def _make_token(
    *,
    secret: str = TEST_SECRET,
    algorithm: str = "HS256",
    sub: str | None = "11111111-1111-4111-8111-111111111111",
    aud: str | None = "authenticated",
    iss: str | None = TEST_ISSUER,
    exp_delta_seconds: float = 3600,
    role: str = "authenticated",
    email: str | None = "user@example.com",
    include_exp: bool = True,
) -> str:
    payload: dict[str, object] = {"role": role}
    if sub is not None:
        payload["sub"] = sub
    if aud is not None:
        payload["aud"] = aud
    if iss is not None:
        payload["iss"] = iss
    if email is not None:
        payload["email"] = email
    if include_exp:
        payload["exp"] = int(time.time() + exp_delta_seconds)
    return jwt.encode(payload, secret, algorithm=algorithm)


def test_verify_access_token_accepts_a_validly_signed_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings())
    token = _make_token()

    user = verify_access_token(token)

    assert user.id == "11111111-1111-4111-8111-111111111111"
    assert user.email == "user@example.com"
    assert user.role == "authenticated"


def test_verify_access_token_fails_closed_when_server_has_no_secret_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings(secret=None))
    token = _make_token()

    with pytest.raises(UnauthorizedError):
        verify_access_token(token)


def test_verify_access_token_fails_closed_when_project_url_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings(supabase_url=None))
    token = _make_token()

    with pytest.raises(UnauthorizedError):
        verify_access_token(token)


def test_verify_access_token_rejects_an_expired_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings())
    token = _make_token(exp_delta_seconds=-3600)

    with pytest.raises(UnauthorizedError):
        verify_access_token(token)


def test_verify_access_token_rejects_wrong_audience(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings())
    token = _make_token(aud="some-other-audience")

    with pytest.raises(UnauthorizedError):
        verify_access_token(token)


def test_verify_access_token_rejects_wrong_issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings())
    token = _make_token(iss="https://a-different-supabase-project.supabase.co/auth/v1")

    with pytest.raises(UnauthorizedError):
        verify_access_token(token)


def test_verify_access_token_rejects_a_token_missing_the_issuer_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings())
    token = _make_token(iss=None)

    with pytest.raises(UnauthorizedError):
        verify_access_token(token)


def test_verify_access_token_rejects_a_token_signed_with_a_different_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings())
    forged_token = _make_token(secret="an-attacker-controlled-secret-also-32bytes+")

    with pytest.raises(UnauthorizedError):
        verify_access_token(forged_token)


def test_verify_access_token_rejects_a_token_missing_the_subject_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings())
    token = _make_token(sub=None)

    with pytest.raises(UnauthorizedError):
        verify_access_token(token)


def test_verify_access_token_rejects_a_token_missing_the_expiry_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings())
    token = _make_token(include_exp=False)

    with pytest.raises(UnauthorizedError):
        verify_access_token(token)


def test_verify_access_token_rejects_a_malformed_token_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings())

    with pytest.raises(UnauthorizedError):
        verify_access_token("this-is-not-a-jwt")


def test_verify_access_token_defaults_role_to_authenticated_when_claim_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings())
    payload = {
        "sub": "22222222-2222-4222-8222-222222222222",
        "aud": "authenticated",
        "iss": TEST_ISSUER,
        "exp": int(time.time() + 3600),
    }
    token = jwt.encode(payload, TEST_SECRET, algorithm="HS256")

    user = verify_access_token(token)

    assert user.role == "authenticated"
    assert user.email is None
