"""
Unit tests for app/core/security.py's verify_access_token() — real
cryptographic JWT verification logic, exercised with TEST-ONLY EC keypairs
minted in-process (never the real Supabase project's signing key, never a
token obtained from the live Supabase project). This is deliberately
"UNIT", not "INTEGRATION", per this phase's testing taxonomy: it proves
the verification LOGIC is correct (signature, expiry, audience, issuer,
required claims, algorithm allowlisting) without needing any real
credentials or network access — real Supabase-issued tokens are exercised
separately in tests/test_auth_api.py (integration).

The JWKS HTTP lookup itself (app.core.security._get_jwks_client) is
replaced with a fake (see tests/_jwt_test_helpers.py) so no network call
happens — see that file's docstring for exactly what trust boundary this
does and doesn't re-test.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.exceptions import UnauthorizedError
from app.core.security import verify_access_token
from tests._jwt_test_helpers import (
    OTHER_PRIVATE_KEY,
    TEST_SUPABASE_URL,
    FailingJWKSClient,
    FakeJWKSClient,
    make_signing_key,
    make_token,
)


def _settings(supabase_url: str | None = TEST_SUPABASE_URL) -> Settings:
    return Settings(_env_file=None, supabase_url=supabase_url)


def _patch_jwks_client(monkeypatch: pytest.MonkeyPatch, client: object) -> None:
    monkeypatch.setattr("app.core.security._get_jwks_client", lambda url: client)


def test_verify_access_token_accepts_a_validly_signed_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings())
    _patch_jwks_client(monkeypatch, FakeJWKSClient(make_signing_key()))
    token = make_token()

    user = verify_access_token(token)

    assert user.id == "11111111-1111-4111-8111-111111111111"
    assert user.email == "user@example.com"
    assert user.role == "authenticated"


def test_verify_access_token_fails_closed_when_project_url_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings(supabase_url=None))
    token = make_token()

    with pytest.raises(UnauthorizedError):
        verify_access_token(token)


def test_verify_access_token_fails_closed_when_jwks_lookup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers an unreachable JWKS endpoint, or a token whose `kid` matches
    no currently-known signing key (e.g. one rotated out by Supabase)."""
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings())
    _patch_jwks_client(monkeypatch, FailingJWKSClient())
    token = make_token()

    with pytest.raises(UnauthorizedError):
        verify_access_token(token)


def test_verify_access_token_rejects_a_key_with_a_disallowed_algorithm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defense-in-depth: even if a JWKS response somehow served a
    symmetric (HS256/"oct") key, verify_access_token must refuse it rather
    than using it to verify a signature — accepting a symmetric key here
    would defeat the entire point of asymmetric verification (classic
    algorithm-confusion attack surface)."""
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings())

    class _SpoofedHS256Key:
        algorithm_name = "HS256"
        key = "irrelevant-never-reached"

    _patch_jwks_client(monkeypatch, FakeJWKSClient(_SpoofedHS256Key()))  # type: ignore[arg-type]
    token = make_token()

    with pytest.raises(UnauthorizedError):
        verify_access_token(token)


def test_verify_access_token_rejects_an_expired_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings())
    _patch_jwks_client(monkeypatch, FakeJWKSClient(make_signing_key()))
    token = make_token(exp_delta_seconds=-3600)

    with pytest.raises(UnauthorizedError):
        verify_access_token(token)


def test_verify_access_token_rejects_wrong_audience(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings())
    _patch_jwks_client(monkeypatch, FakeJWKSClient(make_signing_key()))
    token = make_token(aud="some-other-audience")

    with pytest.raises(UnauthorizedError):
        verify_access_token(token)


def test_verify_access_token_rejects_wrong_issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings())
    _patch_jwks_client(monkeypatch, FakeJWKSClient(make_signing_key()))
    token = make_token(iss="https://a-different-supabase-project.supabase.co/auth/v1")

    with pytest.raises(UnauthorizedError):
        verify_access_token(token)


def test_verify_access_token_rejects_a_token_missing_the_issuer_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings())
    _patch_jwks_client(monkeypatch, FakeJWKSClient(make_signing_key()))
    token = make_token(iss=None)

    with pytest.raises(UnauthorizedError):
        verify_access_token(token)


def test_verify_access_token_rejects_a_token_signed_with_a_different_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The forged token is signed with OTHER_PRIVATE_KEY, but the (fake)
    JWKS lookup still resolves to PRIMARY's public key — exactly the real
    scenario this guards against: an attacker cannot get their own key
    accepted just by presenting a token, since verification always uses
    the key resolved from OUR project's own trusted JWKS endpoint."""
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings())
    _patch_jwks_client(monkeypatch, FakeJWKSClient(make_signing_key()))  # PRIMARY's public key
    forged_token = make_token(private_key=OTHER_PRIVATE_KEY)

    with pytest.raises(UnauthorizedError):
        verify_access_token(forged_token)


def test_verify_access_token_rejects_a_token_missing_the_subject_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings())
    _patch_jwks_client(monkeypatch, FakeJWKSClient(make_signing_key()))
    token = make_token(sub=None)

    with pytest.raises(UnauthorizedError):
        verify_access_token(token)


def test_verify_access_token_rejects_a_token_missing_the_expiry_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings())
    _patch_jwks_client(monkeypatch, FakeJWKSClient(make_signing_key()))
    token = make_token(include_exp=False)

    with pytest.raises(UnauthorizedError):
        verify_access_token(token)


def test_verify_access_token_rejects_a_malformed_token_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings())
    _patch_jwks_client(monkeypatch, FakeJWKSClient(make_signing_key()))

    with pytest.raises(UnauthorizedError):
        verify_access_token("this-is-not-a-jwt")


def test_verify_access_token_defaults_role_to_authenticated_when_claim_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.security.get_settings", lambda: _settings())
    _patch_jwks_client(monkeypatch, FakeJWKSClient(make_signing_key()))
    token = make_token(sub="22222222-2222-4222-8222-222222222222", role=None, email=None)

    user = verify_access_token(token)

    assert user.role == "authenticated"
    assert user.email is None
