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

    # --- Places, second provider (Maps-only integration phase) ---
    # Geoapify Places API key, used exclusively by
    # app/services/geoapify_places_client.py, following the exact same
    # "server-side only, never sent to the mobile client" rule as
    # google_maps_api_key above. Geoapify is currently used for
    # location-based ("nearby") place discovery only — Geoapify's Places
    # API has no free-text query parameter (that needs Geoapify's
    # Geocoding API, not yet authorized/configured — see
    # docs/PHASE_STATUS.md's Maps Integration phase entry for the full
    # capability audit). When unset, nearby search stays cache/DB-only,
    # exactly as it already degrades today (CLAUDE.md §9).
    geoapify_api_key: SecretStr | None = Field(default=None)

    # --- Weather (F3 H7 fix — outdoor-activity flagging, AI_ARCHITECTURE.md §2) ---
    # OpenWeatherMap key. SecretStr: billable, abusable if leaked. When
    # unset, the weather business-rule step is skipped (itinerary items are
    # not flagged for weather) rather than the whole pipeline failing —
    # documented, graceful degradation, never a hard crash (CLAUDE.md §9).
    weather_api_key: SecretStr | None = Field(default=None)

    # --- AI / LLM Gateway (Phase 6 — F3/F4/F5, AI_ARCHITECTURE.md §1) ---
    # Provider is a config value, never a hardcoded vendor dependency: every
    # AI-facing service in this codebase is written against the
    # `LLMGateway` protocol (app/services/ai/llm_gateway.py), never against
    # a vendor SDK directly. Google Gemini is the provider selected for
    # this project (documented decision, this phase) — `llm_provider`
    # exists so a future provider swap is a config change, not a rewrite.
    llm_provider: Literal["gemini"] = "gemini"
    gemini_api_key: SecretStr | None = Field(default=None)
    # Model tiers are independently configurable per AI_ARCHITECTURE.md §12
    # ("model tier is configurable per pipeline") — a cheaper/faster model
    # for structured extraction/generation, a stronger one for
    # conversational nuance, a dedicated embedding model whose output
    # dimension MUST match the vector(1536) columns in DATABASE_SCHEMA.md.
    #
    # REAL, LIVE-TESTING-DISCOVERED CONFIGURATION FIX (Phase 6 certification
    # pass): the originally-configured `gemini-2.5-flash`/`gemini-2.5-pro`
    # both returned a real, live `404 NOT_FOUND` — "no longer available to
    # new users" — from the actual Gemini API against this project's real
    # key, each pointing at a specific named replacement. `gemini-3.1-pro-preview`
    # (the suggested pro replacement) was tried and returned a real `429`
    # with an explicit `limit: 0` free-tier quota for that model — the "pro"
    # tier is not usable at all on this key's current plan, not just rate-
    # limited. `gemini-flash-latest` (a Google-maintained alias, not a dated
    # snapshot, reducing future deprecation churn) was verified live to work
    # for both text and reasoning roles under this key/plan — both settings
    # point at it until a paid tier or a specific stronger model is
    # confirmed available.
    gemini_text_model: str = "gemini-flash-latest"
    gemini_reasoning_model: str = "gemini-flash-latest"
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_embedding_dimensions: int = 1536

    # --- Safety/SOS trusted-contact email (Phase 8 — F21, IMPLEMENTATION_BLUEPRINT.md
    # F21's "SMS/email provider for trusted-contact notification if contact
    # isn't an app user"). No specific commercial SMS vendor was ever
    # decided anywhere in the seven engineering documents, so SMS delivery
    # is NOT implemented here (documented BLOCKED, PHASE_STATUS.md) rather
    # than fabricated against an unspecified provider. Email uses a plain
    # SMTP client (stdlib smtplib, app/services/email_client.py) — real,
    # provider-agnostic, works with any SMTP relay via env vars. When
    # unset, SOS still dispatches real Expo push + writes the sos_events
    # row; only the non-app-user email leg degrades (never a hard failure).
    smtp_host: str | None = Field(default=None)
    smtp_port: int = 587
    smtp_username: str | None = Field(default=None)
    smtp_password: SecretStr | None = Field(default=None)
    smtp_from_email: str | None = Field(default=None)

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — env is read once per process."""
    return Settings()
