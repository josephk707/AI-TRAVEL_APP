"""
Live database verification — this phase's §12 ("Database Verification")
made executable rather than a manual, one-off checklist.

Skipped entirely unless DATABASE_URL is actually set (a real Supabase
project is configured). This is deliberate, per this phase's §11: "do not
fake successful database connectivity." When these tests run, they connect
to the REAL database and inspect its ACTUAL state via information_schema/
pg_catalog — never the migration files themselves, which is exactly what
§12 explicitly warns against ("Do not merely inspect migration files.
Verify the actual database state.").

Run with: DATABASE_URL=postgres://... pytest tests/test_live_database.py -v
"""

from __future__ import annotations

import os

import asyncpg
import pytest

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason=(
        "DATABASE_URL not set — live database verification skipped "
        "(see docs/PHASE_STATUS.md Phase 2: BLOCKED items)"
    ),
)

EXPECTED_EXTENSIONS = {"uuid-ossp", "pgcrypto", "vector", "postgis"}

EXPECTED_TABLES = {
    "profiles",
    "interests",
    "profile_interests",
    "trips",
    "trip_members",
    "trip_preferences",
    "trip_raw_notes",
    "itinerary_days",
    "itinerary_items",
    "pois",
    "heritage_content",
    "heritage_content_embeddings",
    "phrasebook_entries",
    "memory_items",
    "collections",
    "collection_items",
    "favorites",
    "reviews",
    "notifications",
    "device_push_tokens",
    "budget_expenses",
    "trusted_contacts",
    "trip_location_shares",
    "sos_events",
    "location_pings",
    "feedback_signals",
    "personalization_profile",
    "ai_conversations",
    "ai_messages",
    "weather_cache",
    "disruption_events",
    "quick_plans",
    "quick_plan_items",
    "audit_logs",
    "analytics_events",
    "bookings",
    "trip_recaps",
}

# weather_cache intentionally has RLS NOT enabled at all — service-role-only,
# never client-exposed (see migration 20260825120009's comment).
NO_RLS_TABLES = {"weather_cache"}

# Tables that have RLS ENABLED but intentionally grant NO client-facing
# policies at all (service-role-only reads/writes) — checked separately
# from tables that have RLS disabled entirely.
NO_CLIENT_POLICY_TABLES = NO_RLS_TABLES | {
    # fixes L9: raw embeddings are service-role-only, see migration 20260825120003
    "heritage_content_embeddings"
}


@pytest.fixture
async def conn():
    connection = await asyncpg.connect(DATABASE_URL, timeout=10)
    try:
        yield connection
    finally:
        await connection.close()


# ---------------------------------------------------------------------------
# Extensions
# ---------------------------------------------------------------------------
async def test_required_extensions_installed(conn: asyncpg.Connection) -> None:
    rows = await conn.fetch("select extname from pg_extension;")
    installed = {row["extname"] for row in rows}
    missing = EXPECTED_EXTENSIONS - installed
    assert not missing, f"Missing required extensions: {missing}"


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------
async def test_all_expected_tables_exist(conn: asyncpg.Connection) -> None:
    rows = await conn.fetch(
        "select table_name from information_schema.tables "
        "where table_schema = 'public' and table_type = 'BASE TABLE';"
    )
    actual = {row["table_name"] for row in rows}
    missing = EXPECTED_TABLES - actual
    assert not missing, (
        f"Tables defined in DATABASE_SCHEMA.md but missing from the live database: {missing}"
    )


async def test_every_expected_table_has_a_primary_key(conn: asyncpg.Connection) -> None:
    rows = await conn.fetch("""
        select tc.table_name
        from information_schema.table_constraints tc
        where tc.table_schema = 'public' and tc.constraint_type = 'PRIMARY KEY';
        """)
    tables_with_pk = {row["table_name"] for row in rows}
    missing = EXPECTED_TABLES - tables_with_pk
    assert not missing, f"Tables without a primary key: {missing}"


# ---------------------------------------------------------------------------
# Row Level Security — CRITICAL per this phase's §6
# ---------------------------------------------------------------------------
async def test_rls_enabled_on_every_expected_table(conn: asyncpg.Connection) -> None:
    rows = await conn.fetch("""
        select c.relname as table_name, c.relrowsecurity as rls_enabled
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relkind = 'r';
        """)
    rls_status = {row["table_name"]: row["rls_enabled"] for row in rows}
    expected_with_rls = EXPECTED_TABLES - NO_RLS_TABLES
    not_enabled = {t for t in expected_with_rls if not rls_status.get(t, False)}
    assert not not_enabled, f"RLS is NOT enabled on: {not_enabled}"


async def test_every_table_except_documented_exceptions_has_client_policies(
    conn: asyncpg.Connection,
) -> None:
    rows = await conn.fetch(
        "select distinct tablename from pg_policies where schemaname = 'public';"
    )
    tables_with_policies = {row["tablename"] for row in rows}
    expected_with_policies = EXPECTED_TABLES - NO_CLIENT_POLICY_TABLES
    missing = expected_with_policies - tables_with_policies
    assert not missing, f"Tables with RLS but NO policies at all (unintentional?): {missing}"


# ---------------------------------------------------------------------------
# ARCHITECTURE_REVIEW.md fixes — verified against the live schema, not just
# the migration source.
# ---------------------------------------------------------------------------
async def test_c1_fix_profiles_has_pace_column(conn: asyncpg.Connection) -> None:
    row = await conn.fetchrow(
        "select data_type from information_schema.columns "
        "where table_schema = 'public' and table_name = 'profiles' and column_name = 'pace';"
    )
    assert row is not None, "C1 regression: profiles.pace column is missing"


async def test_c2_fix_audit_logs_actor_user_id_on_delete_set_null(conn: asyncpg.Connection) -> None:
    delete_rule = await _fk_delete_rule(conn, "audit_logs", "actor_user_id")
    assert delete_rule == "SET NULL", f"C2 regression: expected SET NULL, got {delete_rule}"


@pytest.mark.parametrize(
    ("table", "column", "expected_rule"),
    [
        ("itinerary_items", "poi_id", "SET NULL"),
        ("quick_plan_items", "poi_id", "CASCADE"),
        ("reviews", "trip_id", "CASCADE"),
        ("sos_events", "trip_id", "CASCADE"),
        ("profile_interests", "interest_id", "CASCADE"),
        ("reviews", "moderated_by", "SET NULL"),
    ],
)
async def test_m2_fix_explicit_on_delete_behavior(
    conn: asyncpg.Connection, table: str, column: str, expected_rule: str
) -> None:
    delete_rule = await _fk_delete_rule(conn, table, column)
    assert delete_rule == expected_rule, (
        f"M2 regression: {table}.{column} expected ON DELETE {expected_rule}, got {delete_rule}"
    )


async def test_m8_fix_ai_messages_conversation_id_nullable_with_context_type(
    conn: asyncpg.Connection,
) -> None:
    row = await conn.fetchrow(
        "select is_nullable from information_schema.columns "
        "where table_schema = 'public' and table_name = 'ai_messages' "
        "and column_name = 'conversation_id';"
    )
    assert row is not None and row["is_nullable"] == "YES", (
        "M8 regression: conversation_id must be nullable"
    )

    context_type_row = await conn.fetchrow(
        "select data_type from information_schema.columns "
        "where table_schema = 'public' and table_name = 'ai_messages' "
        "and column_name = 'context_type';"
    )
    assert context_type_row is not None, "M8 regression: context_type column is missing"


async def test_h6_fix_memory_items_has_separate_mutation_policies(conn: asyncpg.Connection) -> None:
    rows = await conn.fetch(
        "select policyname, cmd from pg_policies "
        "where schemaname = 'public' and tablename = 'memory_items';"
    )
    commands = {row["cmd"] for row in rows}
    # A single old-style "for all" policy would show as ALL; the fix
    # requires distinct SELECT vs INSERT vs UPDATE vs DELETE policies.
    assert {"r", "a", "w", "d"}.issubset(commands) or {
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
    }.issubset(commands), (
        f"H6 regression: memory_items policies are not split per-command: {commands}"
    )


async def test_l9_fix_heritage_embeddings_has_no_client_select_policy(
    conn: asyncpg.Connection,
) -> None:
    rows = await conn.fetch(
        "select policyname from pg_policies "
        "where schemaname = 'public' and tablename = 'heritage_content_embeddings';"
    )
    assert len(rows) == 0, (
        f"L9 regression: client-facing policies exist on heritage_content_embeddings: {rows}"
    )


async def test_l11_fix_pois_and_heritage_content_have_admin_update_delete(
    conn: asyncpg.Connection,
) -> None:
    for table in ("pois", "heritage_content"):
        rows = await conn.fetch(
            "select cmd from pg_policies where schemaname = 'public' and tablename = $1;", table
        )
        commands = {row["cmd"] for row in rows}
        assert "UPDATE" in commands or "w" in commands, (
            f"L11 regression: no admin UPDATE policy on {table}"
        )
        assert "DELETE" in commands or "d" in commands, (
            f"L11 regression: no admin DELETE policy on {table}"
        )


# ---------------------------------------------------------------------------
# Functions (is_trip_member, retention contracts, profile-provisioning trigger)
# ---------------------------------------------------------------------------
async def test_is_trip_member_function_exists(conn: asyncpg.Connection) -> None:
    row = await conn.fetchrow(
        "select proname from pg_proc where proname = 'is_trip_member' "
        "and pronamespace = 'public'::regnamespace;"
    )
    assert row is not None


async def test_retention_contract_functions_exist(conn: asyncpg.Connection) -> None:
    for fn in ("memory_items_due_for_reminder", "location_pings_due_for_purge"):
        row = await conn.fetchrow(
            "select proname from pg_proc "
            "where proname = $1 and pronamespace = 'public'::regnamespace;",
            fn,
        )
        assert row is not None, f"Retention contract function missing: {fn}"


async def test_profile_provisioning_trigger_exists(conn: asyncpg.Connection) -> None:
    row = await conn.fetchrow(
        "select tgname from pg_trigger where tgname = 'on_auth_user_created' and not tgisinternal;"
    )
    assert row is not None, "H1 fix regression: on_auth_user_created trigger is missing"


# ---------------------------------------------------------------------------
# Seed / reference data (curated interests — NOT fake user data)
# ---------------------------------------------------------------------------
async def test_interests_seeded_with_real_curated_values(conn: asyncpg.Connection) -> None:
    count = await conn.fetchval("select count(*) from public.interests;")
    assert count >= 10, f"Expected the curated interests seed (>=10 rows), found {count}"


# ---------------------------------------------------------------------------
# Vector + geospatial foundation
# ---------------------------------------------------------------------------
async def test_vector_columns_exist(conn: asyncpg.Connection) -> None:
    for table, column in (
        ("heritage_content_embeddings", "embedding"),
        ("personalization_profile", "taste_embedding"),
    ):
        row = await conn.fetchrow(
            "select udt_name from information_schema.columns "
            "where table_schema = 'public' and table_name = $1 and column_name = $2;",
            table,
            column,
        )
        assert row is not None and row["udt_name"] == "vector", (
            f"{table}.{column} is not a vector column"
        )


async def test_geography_columns_exist(conn: asyncpg.Connection) -> None:
    for table, column in (("pois", "location"), ("location_pings", "location")):
        row = await conn.fetchrow(
            "select udt_name from information_schema.columns "
            "where table_schema = 'public' and table_name = $1 and column_name = $2;",
            table,
            column,
        )
        assert row is not None and row["udt_name"] == "geography", (
            f"{table}.{column} is not a geography column"
        )


async def test_geospatial_and_vector_indexes_exist(conn: asyncpg.Connection) -> None:
    expected_indexes = {
        "pois_location_gix",
        "location_pings_gix",
        "heritage_embeddings_ivfflat",
    }
    rows = await conn.fetch("select indexname from pg_indexes where schemaname = 'public';")
    actual = {row["indexname"] for row in rows}
    missing = expected_indexes - actual
    assert not missing, f"Missing expected indexes: {missing}"


# ---------------------------------------------------------------------------
# Storage foundation
# ---------------------------------------------------------------------------
async def test_memory_items_storage_bucket_exists_and_is_private(conn: asyncpg.Connection) -> None:
    row = await conn.fetchrow(
        "select public, file_size_limit from storage.buckets where id = 'memory-items';"
    )
    assert row is not None, "memory-items storage bucket does not exist"
    assert row["public"] is False, "memory-items bucket must be private"
    assert row["file_size_limit"] == 26214400


async def test_storage_objects_has_memory_items_policies(conn: asyncpg.Connection) -> None:
    rows = await conn.fetch(
        "select policyname from pg_policies where schemaname = 'storage' "
        "and tablename = 'objects' and policyname like 'memory_items_storage%';"
    )
    assert len(rows) >= 4, f"Expected >=4 memory-items storage policies, found {len(rows)}"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
async def _fk_delete_rule(conn: asyncpg.Connection, table: str, column: str) -> str | None:
    row = await conn.fetchrow(
        """
        select rc.delete_rule
        from information_schema.table_constraints tc
        join information_schema.key_column_usage kcu
          on tc.constraint_name = kcu.constraint_name and tc.table_schema = kcu.table_schema
        join information_schema.referential_constraints rc
          on tc.constraint_name = rc.constraint_name and tc.constraint_schema = rc.constraint_schema
        where tc.table_schema = 'public'
          and tc.table_name = $1
          and kcu.column_name = $2
          and tc.constraint_type = 'FOREIGN KEY';
        """,
        table,
        column,
    )
    return row["delete_rule"] if row else None
