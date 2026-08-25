"""
Applies supabase/migrations/*.sql, in filename order, to the database named
by DATABASE_URL in backend/.env — tracking what has already been applied
in a `public._migrations_applied` bookkeeping table, so re-running this
script is safe/idempotent (only new migration files run) rather than
re-executing already-applied SQL against a live database. This is what
this phase's §1 means by "deterministic, repeatable" — discovered as a
real gap when a second run (after adding a new migration file) tried to
recreate tables that already existed.

SECRET SAFETY (this script exists specifically because a naive shell
`source backend/.env` previously leaked credentials into a terminal
transcript — see docs/PHASE_STATUS.md Phase 2 "known limitations" for the
incident record):
  - DATABASE_URL is loaded via python-dotenv (a real .env parser, not shell
    sourcing) and is NEVER printed, logged, or interpolated into any
    message this script emits.
  - The one call that uses the raw DSN (asyncpg.connect) has its exception
    handling deliberately generic — connection-stage errors are the ones
    most likely to embed the DSN (e.g. DNS/auth failures), so on failure
    this script reports only the exception TYPE, never str(exc).
  - Every other error (a SQL syntax/constraint issue inside a migration,
    once the connection is already open) is safe to print in full — those
    messages describe the SQL, not the connection string.

Usage:
    python scripts/apply_migrations.py [--dry-run]
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"
BACKEND_ENV = REPO_ROOT / "backend" / ".env"

_TRACKING_TABLE_DDL = """
create table if not exists public._migrations_applied (
    filename    text primary key,
    applied_at  timestamptz not null default now()
);
"""


def _redact(text: str) -> str:
    """Defense in depth: strip anything that looks like a postgres DSN
    from a string before it is ever printed, even though the call sites
    that use this are not expected to need it."""
    return re.sub(r"postgres(?:ql)?://[^\s\"']+", "[REDACTED_DSN]", text)


async def main(dry_run: bool) -> int:
    load_dotenv(dotenv_path=BACKEND_ENV)
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        print("DATABASE_URL is not set in backend/.env — nothing to do.")
        return 1

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        print(f"No migration files found in {MIGRATIONS_DIR}")
        return 1

    try:
        conn = await asyncpg.connect(database_url, timeout=15)
    except Exception as exc:  # noqa: BLE001 - deliberately generic, see module docstring
        print(f"\nFAILED to connect to the database ({type(exc).__name__}).")
        print("Check DATABASE_URL in backend/.env — no further detail is printed here")
        print("deliberately, since connection errors can embed the connection string.")
        return 1

    try:
        await conn.execute(_TRACKING_TABLE_DDL)
        already_applied = {
            row["filename"]
            for row in await conn.fetch("select filename from public._migrations_applied;")
        }

        pending = [f for f in migration_files if f.name not in already_applied]

        print(f"Found {len(migration_files)} migration file(s); {len(pending)} pending.")
        for f in migration_files:
            marker = "[already applied]" if f.name in already_applied else "[pending]"
            print(f"  - {f.name} {marker}")

        if dry_run:
            print("\n--dry-run: no statements executed.")
            return 0

        if not pending:
            print("\nNothing to do — all migrations already applied.")
            return 0

        print("\nApplying pending migrations...\n")
        applied_now = []
        for f in pending:
            sql_text = f.read_text(encoding="utf-8")
            print(f"Applying {f.name} ...", end=" ", flush=True)
            try:
                async with conn.transaction():
                    await conn.execute(sql_text)
                    await conn.execute(
                        "insert into public._migrations_applied (filename) values ($1);", f.name
                    )
                print("OK")
                applied_now.append(f.name)
            except Exception as exc:  # noqa: BLE001
                # Safe to print in full: this is a SQL execution error on an
                # already-open connection, not a connection-stage error.
                print("FAILED")
                print(f"  {type(exc).__name__}: {_redact(str(exc))}")
                return 1

        print(f"\n{len(applied_now)} new migration(s) applied successfully.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    exit_code = asyncio.run(main(dry_run=dry))
    sys.exit(exit_code)
