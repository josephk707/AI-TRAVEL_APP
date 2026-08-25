"""
One-off: seeds public._migrations_applied with the 13 migration files that
were already successfully applied to the live database before the
tracking table existed (see apply_migrations.py's history) — so re-running
apply_migrations.py treats only genuinely new files as pending, instead of
re-executing already-applied, non-idempotent `create table` statements.

Same secret-safety rules as apply_migrations.py: DATABASE_URL is loaded via
python-dotenv and never printed; connection errors report only the
exception type.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ENV = REPO_ROOT / "backend" / ".env"

ALREADY_APPLIED = [
    "20260825120001_extensions.sql",
    "20260825120002_profiles_and_interests.sql",
    "20260825120003_pois_and_heritage.sql",
    "20260825120004_trips_and_itinerary.sql",
    "20260825120005_memory_collections_reviews.sql",
    "20260825120006_notifications_budget.sql",
    "20260825120007_safety_and_location.sql",
    "20260825120008_personalization_and_ai.sql",
    "20260825120009_dynamic_and_quickplans.sql",
    "20260825120010_operational.sql",
    "20260825120011_future_stubs.sql",
    "20260825120012_retention_contracts.sql",
    "20260825120013_storage_memory_items.sql",
]


async def main() -> int:
    load_dotenv(dotenv_path=BACKEND_ENV)
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set.")
        return 1

    try:
        conn = await asyncpg.connect(database_url, timeout=15)
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED to connect ({type(exc).__name__}).")
        return 1

    try:
        await conn.execute(
            "create table if not exists public._migrations_applied ("
            "filename text primary key, applied_at timestamptz not null default now());"
        )
        for filename in ALREADY_APPLIED:
            await conn.execute(
                "insert into public._migrations_applied (filename) values ($1) "
                "on conflict (filename) do nothing;",
                filename,
            )
        count = await conn.fetchval("select count(*) from public._migrations_applied;")
        print(f"Tracking table now has {count} recorded migration(s).")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(main()))
