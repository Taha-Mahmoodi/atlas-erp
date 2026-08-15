"""PostgreSQL-only guards (run with `-m pg` against a real Postgres).

These cover what the SQLite test engine cannot: that the per-dialect trigger DDL and
the append-only enforcement actually work on the production database. Regression for
issue #12 — migration 0005's `DROP TRIGGER` used SQLite-only syntax and broke
`alembic upgrade head` on Postgres while every SQLite test stayed green.

Skipped automatically unless ATLAS_DATABASE_URL points at PostgreSQL, so the default
SQLite run never executes them; CI's Postgres step sets that URL and selects `-m pg`.
"""

import asyncio
import os
import uuid
from collections.abc import Callable

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

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


async def test_0046_expresses_its_constraints_on_postgres() -> None:
    """0046's DDL survives translation to the real engine: JSON_VARIANT lands as JSONB, the
    composite tenant FK and both unique constraints exist under their D-022 names, and the
    two indexes are present. SQLite renders all of this differently, so only Postgres can
    prove the shape the runtime actually gets."""
    engine = create_async_engine(_URL)
    try:
        async with engine.connect() as conn:
            scopes_type = await conn.scalar(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name = 'core_api_keys' AND column_name = 'scopes'"
                )
            )
            constraints = set(
                await conn.scalars(
                    text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE conrelid = 'core_api_keys'::regclass"
                    )
                )
            )
            indexes = set(
                await conn.scalars(
                    text("SELECT indexname FROM pg_indexes WHERE tablename = 'core_api_keys'")
                )
            )
    finally:
        await engine.dispose()

    assert scopes_type == "jsonb"
    assert {
        "pk_core_api_keys",
        "uq_core_api_keys_tenant_id",
        "uq_core_api_keys_secret_sha256",
        "fk_core_api_keys_tenant_id_adm_tenants",
        "fk_core_api_keys_tenant_id_core_users",
    } <= constraints
    assert {"ix_core_api_keys_tenant_id", "ix_core_api_keys_tenant_id_user_id"} <= indexes


async def _seed_two_tenants(
    conn: AsyncConnection,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Two tenants, one user each, inside the caller's (always rolled back) transaction."""
    tenant_a, tenant_b, user_a, user_b = (uuid.uuid4() for _ in range(4))
    for tenant_id, user_id in ((tenant_a, user_a), (tenant_b, user_b)):
        await conn.execute(
            text(
                "INSERT INTO adm_tenants (id, slug, name, created_at, updated_at) "
                "VALUES (:id, :slug, :slug, now(), now())"
            ),
            {"id": tenant_id, "slug": f"pg-{tenant_id.hex[:12]}"},
        )
        await conn.execute(
            text(
                "INSERT INTO core_users (id, tenant_id, email, password_hash, "
                "created_at, updated_at) "
                "VALUES (:id, :tid, 'u@example.test', 'x', now(), now())"
            ),
            {"id": user_id, "tid": tenant_id},
        )
    return tenant_a, tenant_b, user_a, user_b


_INSERT_KEY = text(
    "INSERT INTO core_api_keys (id, tenant_id, user_id, name, prefix, secret_sha256, "
    "created_at, updated_at) "
    "VALUES (:id, :tid, :uid, 'k', 'atk_x', :digest, now(), now())"
)


async def test_0046_composite_tenant_fk_rejects_a_foreign_user_on_postgres() -> None:
    """D-007 item 4 on the real engine: (tenant_id, user_id) -> core_users(tenant_id, id)
    stops a key row binding to another tenant's user. The transaction is never committed."""
    engine = create_async_engine(_URL)
    try:
        async with engine.connect() as conn:
            await conn.begin()
            tenant_a, tenant_b, user_a, _ = await _seed_two_tenants(conn)
            # Sanity: the same insert inside the owning tenant is accepted, so the failure
            # below is the composite FK and not an unrelated NOT NULL.
            await conn.execute(
                _INSERT_KEY,
                {"id": uuid.uuid4(), "tid": tenant_a, "uid": user_a, "digest": "a" * 64},
            )
            with pytest.raises(IntegrityError):
                await conn.execute(
                    _INSERT_KEY,
                    {"id": uuid.uuid4(), "tid": tenant_b, "uid": user_a, "digest": "b" * 64},
                )
            await conn.rollback()
    finally:
        await engine.dispose()


async def test_0046_secret_digest_is_unique_across_tenants_on_postgres() -> None:
    """uq_core_api_keys_secret_sha256 is global, not per-tenant: the digest is the auth
    lookup key, so a cross-tenant collision would authenticate the wrong tenant."""
    engine = create_async_engine(_URL)
    digest = "c" * 64
    try:
        async with engine.connect() as conn:
            await conn.begin()
            tenant_a, tenant_b, user_a, user_b = await _seed_two_tenants(conn)
            await conn.execute(
                _INSERT_KEY,
                {"id": uuid.uuid4(), "tid": tenant_a, "uid": user_a, "digest": digest},
            )
            with pytest.raises(IntegrityError):
                await conn.execute(
                    _INSERT_KEY,
                    {"id": uuid.uuid4(), "tid": tenant_b, "uid": user_b, "digest": digest},
                )
            await conn.rollback()
    finally:
        await engine.dispose()


def test_0046_round_trips_on_postgres(make_alembic_config: Callable[[str], Config]) -> None:
    """upgrade -> downgrade -> upgrade on the real engine. Postgres drops a table's indexes
    with it, but this asserts it rather than assuming: a future revision of this migration
    that adds a standalone object (a trigger, an enum type) would leak one silently."""
    config = make_alembic_config(_URL)

    async def _probe() -> tuple[set[str], str | None]:
        engine = create_async_engine(_URL)
        try:
            async with engine.connect() as conn:
                names = set(
                    await conn.scalars(
                        text("SELECT relname FROM pg_class WHERE relname LIKE '%core_api_key%'")
                    )
                )
                version = await conn.scalar(text("SELECT version_num FROM alembic_version"))
            return names, version
        finally:
            await engine.dispose()

    try:
        command.downgrade(config, "0045")
        leftovers, version = asyncio.run(_probe())
        assert leftovers == set(), f"downgrade left objects behind: {sorted(leftovers)}"
        assert version == "0045"
    finally:
        command.upgrade(config, "head")

    restored, version = asyncio.run(_probe())
    # NOT the literal "0046": this asserts that upgrading back reaches whatever head is, so a
    # later migration does not fail a test about 0046's reversibility. Phase 19 added 0047 and
    # 0048 and broke exactly that way.
    assert version == ScriptDirectory.from_config(config).get_current_head()
    assert {
        "core_api_keys",
        "pk_core_api_keys",
        "uq_core_api_keys_tenant_id",
        "uq_core_api_keys_secret_sha256",
        "ix_core_api_keys_tenant_id",
        "ix_core_api_keys_tenant_id_user_id",
    } <= restored
