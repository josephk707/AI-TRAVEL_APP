"""Configuration loading — Phase 1 minimum test coverage (CLAUDE.md §10)."""

from __future__ import annotations

from app.core.config import Settings, get_settings


def test_settings_load_with_safe_defaults() -> None:
    settings = Settings()
    assert settings.app_name
    assert settings.environment in {"development", "testing", "staging", "production"}
    # No secret has a real default value.
    assert settings.database_url is None
    assert settings.supabase_service_role_key is None


def test_cors_origins_list_parses_comma_separated_string() -> None:
    settings = Settings(cors_allow_origins="http://a.test, http://b.test")
    assert settings.cors_origins_list == ["http://a.test", "http://b.test"]


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
