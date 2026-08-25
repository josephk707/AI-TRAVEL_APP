"""One-off: prints the real auth.uid() function definition from the live
database, so the RLS test suite's impersonation technique (SET ROLE +
request.jwt.claims) can be verified against how THIS project actually
implements it, rather than assumed. No secrets involved — function source
code only."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ENV = REPO_ROOT / "backend" / ".env"


async def main() -> None:
    load_dotenv(dotenv_path=BACKEND_ENV)
    conn = await asyncpg.connect(os.environ["DATABASE_URL"], timeout=15)
    try:
        row = await conn.fetchrow(
            "select pg_get_functiondef(oid) as def from pg_proc "
            "where proname = 'uid' and pronamespace = 'auth'::regnamespace;"
        )
        print(row["def"] if row else "auth.uid() not found")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
