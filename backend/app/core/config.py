"""
Application configuration.

Settings are loaded from environment variables (and a local .env file in
development, never committed — see backend/.env.example). No secret ever has
a real default here; anything sensitive defaults to empty/None and is
required to be supplied by the environment.

Genuine secrets (database_url embeds a password; supabase_service_role_key
bypasses RLS entirely) are typed as pydantic.SecretStr, not str. This is
not decorative: SecretStr's __repr__/__str__ print "**********" instead of
the real value, which means an accidental print(settings), a pytest
assertion-failure diff that reprs the object, a debugger, or a log
statement CANNOT leak the value even if someone forgets to be careful —
the leak is prevented structurally rather than relying on every call site
remembering not to. (This project hit exactly this failure mode once
before SecretStr was added here — see docs/PHASE_STATUS.md Phase 2 "known
limitations" for the incident record — which is why this isn't a
theoretical concern.) supabase_url and supabase_anon_key stay plain str:
both are designed by Supabase to be public/embeddable in client apps, not
secrets.

Phase 1 scope: configuration loading only. Nothing here implements auth,
schema, or business logic — see docs/DEPLOYMENT_PLAN.md §4 for the full
secrets-management plan this will grow into.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
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

    # --- Database connection (Phase 2: real schema exists) ---
    # Direct Postgres connection string (Supabase exposes this per-project).
    # SecretStr: contains the database password. Left unset in
    # local/dev-without-Supabase; readiness reports "not_configured" rather
    # than failing when absent.
    database_url: SecretStr | None = Field(default=None)

    # Supabase project coordinates.
    supabase_url: str | None = Field(default=None)
    supabase_anon_key: str | None = Field(default=None)  # public/publishable by design
    supabase_service_role_key: SecretStr | None = Field(default=None)  # bypasses RLS — real secret

    # --- Auth (Phase 3) ---
    # No JWT signing secret is configured here. This project's Supabase
    # instance uses the newer asymmetric "JWT Signing Keys" system (ES256),
    # verified via the project's public JWKS endpoint
    # ({supabase_url}/auth/v1/.well-known/jwks.json) — see
    # app/core/security.py's module docstring for the full architecture
    # decision. Verification needs only supabase_url (above), never a
    # secret: a shared HS256 secret cannot verify an asymmetrically-signed
    # token, so this project intentionally has no SUPABASE_JWT_SECRET
    # setting.

    # --- Maps & Navigation (F6) ---
    # Server-side Google Maps Platform key (Places API "New" enabled) used
    # exclusively by app/services/google_places_client.py — never sent to
    # the mobile client (API_SPECIFICATION.md §5, MOBILE_ARCHITECTURE.md
    # §8). SecretStr: a real, billable, abusable credential. When unset,
    # POI search degrades to cache/curated-only results rather than
    # failing (app/services/poi_service.py) — there is no environment in
    # which this being absent should crash the API.
    google_maps_api_key: SecretStr | None = Field(default=None)

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — env is read once per process."""
    return Settings()
