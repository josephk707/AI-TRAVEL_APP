"""
Real, cross-user Row Level Security verification — this phase's §13
("Security Testing") and §6's explicit test matrix:

  TEST A: authenticated user can access their own permitted records
  TEST B: User A cannot access User B's private records
  TEST C: User A cannot modify User B's private records
  TEST D: User A cannot delete User B's private records
  TEST E: unauthenticated access is rejected where required
  TEST F: ownership cannot be bypassed via a client-supplied identifier

Skipped entirely unless DATABASE_URL, SUPABASE_URL and
SUPABASE_SERVICE_ROLE_KEY are all set. When it runs, it:

  1. Creates two REAL, ephemeral Supabase Auth users via the Admin API
     (service-role key) — this also live-verifies the H1 fix, since the
     on_auth_user_created trigger must fire and provision a `profiles` row
     for each.
  2. Impersonates each user on a raw Postgres connection using the exact
     mechanism Supabase's own PostgREST layer uses (`SET ROLE authenticated`
     + the `request.jwt.claims` session GUC that `auth.uid()` reads) — this
     exercises the REAL RLS policies under a REAL non-superuser role
     boundary, not a mock or an application-layer simulation.
  3. Deletes both users (and their cascade-owned rows) in a finally block —
     these are ephemeral test fixtures, not committed seed data, and are
     never left behind after the run (CLAUDE.md §3's "no fake seed
     users/data" is about permanent migration content, not disposable
     test fixtures created and torn down by the test suite itself — see
     docs/PHASE_STATUS.md Phase 2 section for this distinction spelled out).

Run with (all three required):
  DATABASE_URL=... SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... \
    pytest tests/test_rls_security.py -v
"""

from __future__ import annotations

import json
import os
import uuid

import asyncpg
import httpx
import pytest

DATABASE_URL = os.environ.get("DATABASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

pytestmark = pytest.mark.skipif(
    not (DATABASE_URL and SUPABASE_URL and SERVICE_ROLE_KEY),
    reason=(
        "DATABASE_URL / SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not fully set — "
        "RLS security tests skipped (see docs/PHASE_STATUS.md Phase 2: BLOCKED items)"
    ),
)


# ---------------------------------------------------------------------------
# Ephemeral test-user fixtures (Admin API — real accounts, torn down after)
# ---------------------------------------------------------------------------
async def _admin_headers() -> dict[str, str]:
    return {"apikey": SERVICE_ROLE_KEY, "Authorization": f"Bearer {SERVICE_ROLE_KEY}"}


async def _create_test_user(client: httpx.AsyncClient, tag: str) -> str:
    email = f"rls-test-{tag}-{uuid.uuid4().hex[:10]}@example.invalid"
    response = await client.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers=await _admin_headers(),
        json={"email": email, "email_confirm": True, "password": uuid.uuid4().hex},
    )
    response.raise_for_status()
    return response.json()["id"]


async def _delete_test_user(client: httpx.AsyncClient, user_id: str) -> None:
    response = await client.delete(
        f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}", headers=await _admin_headers()
    )
    # 404 is fine (already gone); anything else we want to know about but
    # never let cleanup failure mask the actual test result.
    if response.status_code not in (200, 204, 404):
        response.raise_for_status()


@pytest.fixture
async def two_users():
    async with httpx.AsyncClient(timeout=15) as client:
        user_a = await _create_test_user(client, "a")
        user_b = await _create_test_user(client, "b")
        try:
            yield user_a, user_b
        finally:
            await _delete_test_user(client, user_a)
            await _delete_test_user(client, user_b)


@pytest.fixture
async def service_conn():
    """Superuser/service connection — bypasses RLS, used only for
    fixture setup/teardown and for asserting ground truth, never for the
    actual security assertions themselves."""
    conn = await asyncpg.connect(DATABASE_URL, timeout=10)
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture
async def user_conn():
    """A fresh connection per test for RLS-impersonated queries."""
    conn = await asyncpg.connect(DATABASE_URL, timeout=10)
    try:
        yield conn
    finally:
        await conn.close()


async def _as_user(conn: asyncpg.Connection, user_id: str) -> None:
    await conn.execute("set role authenticated;")
    claims = json.dumps({"sub": str(user_id), "role": "authenticated"})
    # is_local=false (SESSION-scoped, not SET LOCAL / transaction-scoped):
    # each test issues multiple separate statements after impersonating a
    # user, each of which is its own implicit transaction on this
    # connection. is_local=true previously reset the claim after the first
    # statement, silently making auth.uid() NULL for everything after —
    # which made every negative-outcome test (B/C/D/E/F) "pass" for the
    # wrong reason (a null uid also matches nothing) and only the two
    # positive-match tests (A, H6) exposed it. See docs/PHASE_STATUS.md
    # Phase 2 for the full incident writeup.
    await conn.execute("select set_config('request.jwt.claims', $1, false);", claims)


async def _as_anonymous(conn: asyncpg.Connection) -> None:
    await conn.execute("set role anon;")
    await conn.execute("select set_config('request.jwt.claims', '{}', false);")


_INSERT_TRIP_SQL = (
    "insert into public.trips (owner_id, title, destination) values ($1, $2, 'Agra') returning id;"
)


async def _insert_trip(conn: asyncpg.Connection, owner_id: str, title: str) -> object:
    return await conn.fetchval(_INSERT_TRIP_SQL, uuid.UUID(owner_id), title)


# ---------------------------------------------------------------------------
# H1 regression check, incidental to fixture creation: profile auto-provisioned
# ---------------------------------------------------------------------------
async def test_h1_profile_auto_provisioned_on_user_creation(
    two_users: tuple[str, str], service_conn: asyncpg.Connection
) -> None:
    user_a, _user_b = two_users
    row = await service_conn.fetchrow(
        "select id from public.profiles where id = $1;", uuid.UUID(user_a)
    )
    assert (
        row is not None
    ), "H1 regression: on_auth_user_created trigger did not provision a profiles row"


# ---------------------------------------------------------------------------
# TEST A — owner can access their own record
# ---------------------------------------------------------------------------
async def test_a_owner_can_read_own_trip(
    two_users: tuple[str, str], service_conn: asyncpg.Connection, user_conn: asyncpg.Connection
) -> None:
    user_a, _ = two_users
    trip_id = await _insert_trip(service_conn, user_a, "A's trip")
    try:
        await _as_user(user_conn, user_a)
        row = await user_conn.fetchrow("select id from public.trips where id = $1;", trip_id)
        assert row is not None, "TEST A failed: owner could not read their own trip"
    finally:
        await service_conn.execute("delete from public.trips where id = $1;", trip_id)


# ---------------------------------------------------------------------------
# TEST B — User A cannot read User B's private record
# ---------------------------------------------------------------------------
async def test_b_user_cannot_read_other_users_trip(
    two_users: tuple[str, str], service_conn: asyncpg.Connection, user_conn: asyncpg.Connection
) -> None:
    user_a, user_b = two_users
    trip_id = await _insert_trip(service_conn, user_a, "A's private trip")
    try:
        await _as_user(user_conn, user_b)
        rows = await user_conn.fetch("select id from public.trips where id = $1;", trip_id)
        assert rows == [], "TEST B failed: User B could read User A's private trip"
    finally:
        await service_conn.execute("delete from public.trips where id = $1;", trip_id)


# ---------------------------------------------------------------------------
# TEST C — User A cannot modify User B's record
# ---------------------------------------------------------------------------
async def test_c_user_cannot_update_other_users_trip(
    two_users: tuple[str, str], service_conn: asyncpg.Connection, user_conn: asyncpg.Connection
) -> None:
    user_a, user_b = two_users
    trip_id = await _insert_trip(service_conn, user_a, "Original title")
    try:
        await _as_user(user_conn, user_b)
        result = await user_conn.execute(
            "update public.trips set title = 'Hijacked' where id = $1;", trip_id
        )
        affected = int(result.split()[-1])
        assert affected == 0, "TEST C failed: User B updated User A's trip"

        title = await service_conn.fetchval(
            "select title from public.trips where id = $1;", trip_id
        )
        assert title == "Original title", "TEST C failed: trip title was changed despite RLS"
    finally:
        await service_conn.execute("delete from public.trips where id = $1;", trip_id)


# ---------------------------------------------------------------------------
# TEST D — User A cannot delete User B's record
# ---------------------------------------------------------------------------
async def test_d_user_cannot_delete_other_users_trip(
    two_users: tuple[str, str], service_conn: asyncpg.Connection, user_conn: asyncpg.Connection
) -> None:
    user_a, user_b = two_users
    trip_id = await _insert_trip(service_conn, user_a, "Do not delete me")
    try:
        await _as_user(user_conn, user_b)
        result = await user_conn.execute("delete from public.trips where id = $1;", trip_id)
        affected = int(result.split()[-1])
        assert affected == 0, "TEST D failed: User B deleted User A's trip"

        still_exists = await service_conn.fetchval(
            "select count(*) from public.trips where id = $1;", trip_id
        )
        assert still_exists == 1, "TEST D failed: trip was actually deleted despite RLS"
    finally:
        await service_conn.execute("delete from public.trips where id = $1;", trip_id)


# ---------------------------------------------------------------------------
# TEST E — unauthenticated access is rejected
# ---------------------------------------------------------------------------
async def test_e_unauthenticated_access_rejected(
    two_users: tuple[str, str], service_conn: asyncpg.Connection, user_conn: asyncpg.Connection
) -> None:
    user_a, _ = two_users
    trip_id = await _insert_trip(service_conn, user_a, "Private")
    try:
        await _as_anonymous(user_conn)
        rows = await user_conn.fetch("select id from public.trips where id = $1;", trip_id)
        assert rows == [], "TEST E failed: unauthenticated connection could read a private trip"
    finally:
        await service_conn.execute("delete from public.trips where id = $1;", trip_id)


# ---------------------------------------------------------------------------
# TEST F — ownership cannot be bypassed via a client-supplied identifier
# ---------------------------------------------------------------------------
async def test_f_cannot_insert_claiming_other_users_ownership(
    two_users: tuple[str, str], service_conn: asyncpg.Connection, user_conn: asyncpg.Connection
) -> None:
    user_a, user_b = two_users
    await _as_user(user_conn, user_b)

    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
        # User B trying to insert a trip "owned" by User A.
        await _insert_trip(user_conn, user_a, "Spoofed")

    orphan = await service_conn.fetchval(
        "select count(*) from public.trips where owner_id = $1 and title = 'Spoofed';",
        uuid.UUID(user_a),
    )
    assert orphan == 0, "TEST F failed: spoofed-ownership row was actually inserted"


# ---------------------------------------------------------------------------
# H6 live verification: shared viewing, author-restricted mutation
# ---------------------------------------------------------------------------
async def test_h6_group_member_can_view_but_not_delete_others_memory_item(
    two_users: tuple[str, str], service_conn: asyncpg.Connection, user_conn: asyncpg.Connection
) -> None:
    user_a, user_b = two_users
    trip_id = await service_conn.fetchval(
        "insert into public.trips (owner_id, title, destination, trip_type) "
        "values ($1, 'Group trip', 'Kerala', 'group') returning id;",
        uuid.UUID(user_a),
    )
    await service_conn.execute(
        "insert into public.trip_members (trip_id, user_id, role, invite_status) "
        "values ($1, $2, 'member', 'accepted');",
        trip_id,
        uuid.UUID(user_b),
    )
    memory_item_id = await service_conn.fetchval(
        "insert into public.memory_items (trip_id, user_id, item_type, caption) "
        "values ($1, $2, 'note', 'A''s private memory') returning id;",
        trip_id,
        uuid.UUID(user_a),
    )
    try:
        # User B (an accepted, non-owning member) CAN see it — shared viewing is intended.
        await _as_user(user_conn, user_b)
        visible = await user_conn.fetchrow(
            "select id from public.memory_items where id = $1;", memory_item_id
        )
        assert visible is not None, "H6 check failed: trip member could not view shared memory item"

        # But User B CANNOT delete User A's memory item — this is the actual H6 fix.
        result = await user_conn.execute(
            "delete from public.memory_items where id = $1;", memory_item_id
        )
        affected = int(result.split()[-1])
        assert affected == 0, "H6 REGRESSION: a co-member deleted another member's memory item"

        still_exists = await service_conn.fetchval(
            "select count(*) from public.memory_items where id = $1;", memory_item_id
        )
        assert still_exists == 1, "H6 REGRESSION: memory item was actually deleted by a co-member"
    finally:
        await service_conn.execute("delete from public.memory_items where id = $1;", memory_item_id)
        await service_conn.execute("delete from public.trip_members where trip_id = $1;", trip_id)
        await service_conn.execute("delete from public.trips where id = $1;", trip_id)


# ---------------------------------------------------------------------------
# Phase 3, TEST 4-6: cross-user `profiles` isolation.
#
# No API endpoint lets one authenticated user address another user's
# profile by id (every /v1/auth/* route derives the target row from the
# verified token's own subject — app/repositories/profiles_repository.py),
# so there is no application-layer surface to exercise this against. RLS
# is therefore the ONLY enforcement layer for these three cases, verified
# here directly at the data layer with the same real-ephemeral-user +
# JWT-claim-impersonation technique as TEST A-F above.
# ---------------------------------------------------------------------------
async def test_profiles_owner_can_read_own_profile(
    two_users: tuple[str, str], user_conn: asyncpg.Connection
) -> None:
    user_a, _ = two_users
    await _as_user(user_conn, user_a)
    row = await user_conn.fetchrow(
        "select id from public.profiles where id = $1;", uuid.UUID(user_a)
    )
    assert row is not None, "profiles TEST failed: owner could not read their own profile"


async def test_profiles_user_cannot_read_other_users_profile(
    two_users: tuple[str, str], user_conn: asyncpg.Connection
) -> None:
    user_a, user_b = two_users
    await _as_user(user_conn, user_b)
    rows = await user_conn.fetch("select id from public.profiles where id = $1;", uuid.UUID(user_a))
    assert rows == [], "profiles TEST failed: User B could read User A's profile"


async def test_profiles_user_cannot_update_other_users_profile(
    two_users: tuple[str, str], service_conn: asyncpg.Connection, user_conn: asyncpg.Connection
) -> None:
    user_a, user_b = two_users
    await _as_user(user_conn, user_b)
    result = await user_conn.execute(
        "update public.profiles set display_name = 'Hijacked' where id = $1;",
        uuid.UUID(user_a),
    )
    affected = int(result.split()[-1])
    assert affected == 0, "profiles TEST failed: User B updated User A's profile"

    display_name = await service_conn.fetchval(
        "select display_name from public.profiles where id = $1;", uuid.UUID(user_a)
    )
    assert display_name != "Hijacked", "profiles TEST failed: display_name was changed despite RLS"


async def test_profiles_user_cannot_delete_other_users_profile(
    two_users: tuple[str, str], service_conn: asyncpg.Connection, user_conn: asyncpg.Connection
) -> None:
    user_a, user_b = two_users
    await _as_user(user_conn, user_b)
    result = await user_conn.execute(
        "delete from public.profiles where id = $1;", uuid.UUID(user_a)
    )
    affected = int(result.split()[-1])
    assert affected == 0, "profiles TEST failed: User B deleted User A's profile"

    still_exists = await service_conn.fetchval(
        "select count(*) from public.profiles where id = $1;", uuid.UUID(user_a)
    )
    assert still_exists == 1, "profiles TEST failed: profile was actually deleted despite RLS"
