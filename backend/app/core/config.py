"""
Application configuration.

Settings are loaded from environment variables (and a local .env file in
development, never committed — see backend/.env.example). No secret ever has
a real default here; anything sensitive defaults to empty/None and is
required to be supplied by the environment.

Phase 1 scope: configuration loading only. Nothing here implements auth,
schema, or business logic — see docs/DEPLOYMENT_PLAN.md §4 for the full
secrets-management plan this will grow into.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App identity ---
    app_name: str = "TC-SO1 Backend"
    app_version: str = "0.1.0"
    environment: Literal["development", "testing", "staging", "production"] = "development"

    # --- API ---
    api_v1_prefix: str = "/v1"

    # --- CORS ---
    # Comma-separated list of allowed origins. Defaults cover local Expo dev
    # server ports only — never wildcard "*" once real auth exists.
    cors_allow_origins: str = "http://localhost:19006,http://localhost:8081"

    # --- Logging ---
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # --- Database connection foundation (Phase 1: config only, no schema) ---
    # Direct Postgres connection string (Supabase exposes this per-project).
    # Left unset in local/dev-without-Supabase; readiness reports
    # "not_configured" rather than failing when absent.
    database_url: str | None = Field(default=None)

    # Supabase project coordinates — placeholders until Phase 2/3 wire real
    # values. Never given a real default.
    supabase_url: str | None = Field(default=None)
    supabase_anon_key: str | None = Field(default=None)
    supabase_service_role_key: str | None = Field(default=None)

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — env is read once per process."""
    return Settings()
