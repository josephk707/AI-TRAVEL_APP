"""Configuration loading (CLAUDE.md §10).

These tests are deliberately hermetic — they check the Settings CLASS
definition (declared field defaults, field types) rather than instantiating
Settings() and asserting on live values, specifically so they pass/fail
consistently regardless of what backend/.env actually contains in a given
developer's environment (this file previously assumed DATABASE_URL was
always unset in the test environment, which broke — see
docs/PHASE_STATUS.md Phase 2 "known limitations" — the moment a real
Supabase project was configured for live-database testing)."""

from __future__ import annotations

from pydantic import SecretStr

from app.core.config import Settings, get_settings


def test_settings_load_with_safe_defaults() -> None:
    settings = Settings()
    assert settings.app_name
    assert settings.environment in {"development", "testing", "staging", "production"}


def test_no_secret_field_has_a_real_default_value() -> None:
    """Checked against the class's declared defaults, not a live instance —
    true regardless of whether this environment's backend/.env happens to
    have real credentials configured."""
    for field_name in ("database_url", "supabase_service_role_key"):
        assert Settings.model_fields[field_name].default is None


def test_secret_fields_are_secretstr_not_plain_str() -> None:
    """The structural fix for this project's credential-exposure incident:
    these fields must never be plain str, so an accidental repr/print/log
    of the Settings object cannot leak them (SecretStr prints
    "**********" instead)."""
    for field_name in ("database_url", "supabase_service_role_key"):
        annotation = Settings.model_fields[field_name].annotation
        assert SecretStr in getattr(annotation, "__args__", (annotation,))


def test_secretstr_repr_never_contains_the_real_value() -> None:
    settings = Settings(database_url="postgresql://user:topsecret@host/db")
    assert "topsecret" not in repr(settings)
    assert "topsecret" not in str(settings)
    assert settings.database_url.get_secret_value() == "postgresql://user:topsecret@host/db"


def test_cors_origins_list_parses_comma_separated_string() -> None:
    settings = Settings(cors_allow_origins="http://a.test, http://b.test")
    assert settings.cors_origins_list == ["http://a.test", "http://b.test"]


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
