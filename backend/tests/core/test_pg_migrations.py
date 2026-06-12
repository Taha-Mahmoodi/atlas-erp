"""PostgreSQL-only guards (run with `-m pg` against a real Postgres).

These cover what the SQLite test engine cannot: that the per-dialect trigger DDL and
the append-only enforcement actually work on the production database. Regression for
issue #12 — migration 0005's `DROP TRIGGER` used SQLite-only syntax and broke
`alembic upgrade head` on Postgres while every SQLite test stayed green.

Skipped automatically unless ATLAS_DATABASE_URL points at PostgreSQL, so the default
SQLite run never executes them; CI's Postgres step sets that URL and selects `-m pg`.
"""

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.pg

_URL = os.environ.get("ATLAS_DATABASE_URL", "")

if not _URL.startswith("postgresql"):
    pytest.skip("pg-marked tests require a PostgreSQL ATLAS_DATABASE_URL", allow_module_level=True)


async def test_append_only_trigger_blocks_update_and_delete_on_postgres() -> None:
    """The append-only trigger raises ATLAS_AUDIT_APPEND_ONLY on Postgres (issue #12:
    proves the trigger that migration 0005 installs is actually present and firing on
    the real engine, after a clean `alembic upgrade head`)."""
    engine = create_async_engine(_URL)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO core_audit_log (id, tenant_id, entity_table, entity_id, "
                    "action, diff, created_at, updated_at) "
                    "VALUES (:id, :tid, 't', '1', 'INSERT', '{}', now(), now())"
                ),
                {"id": uuid.uuid4(), "tid": uuid.uuid4()},
            )

        async with engine.connect() as conn:
            with pytest.raises(DBAPIError) as update_err:
                await conn.execute(text("UPDATE core_audit_log SET action = 'X'"))
            assert "ATLAS_AUDIT_APPEND_ONLY" in str(update_err.value)
            await conn.rollback()

            with pytest.raises(DBAPIError) as delete_err:
                await conn.execute(text("DELETE FROM core_audit_log"))
            assert "ATLAS_AUDIT_APPEND_ONLY" in str(delete_err.value)
            await conn.rollback()
    finally:
        await engine.dispose()


async def test_core_schema_present_after_upgrade_head_on_postgres() -> None:
    """A clean upgrade leaves the expected core tables on Postgres — a smoke check that
    the whole migration chain (composite FKs, partial indexes, triggers) applied."""
    engine = create_async_engine(_URL)
    expected = {
        "adm_tenants",
        "core_users",
        "core_roles",
        "core_audit_log",
        "core_number_sequences",
        "core_documents",
        "core_idempotency_keys",
    }
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
            tables = {r[0] for r in rows}
    finally:
        await engine.dispose()
    missing = expected - tables
    assert not missing, f"missing tables after upgrade head: {missing}"
