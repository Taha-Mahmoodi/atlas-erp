"""Split-phase audit capture (D-010), proven through real sessions on the migrated
template database: INSERT/UPDATE/DELETE diffs, request context, system writes, the
append-only triggers + envelope translation, the bulk-write guard, tenant isolation,
and same-transaction atomicity."""

import uuid

import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import app.core.audit as audit
from app.core.audit import json_safe
from app.core.exceptions import AtlasError, translate_db_guard_error
from app.core.models import AuditLog, User
from app.core.tenancy import system_context, tenant_context
from app.main import create_app


async def _make_user(
    session: AsyncSession, tenant_id: uuid.UUID, email: str = "a@acme.test"
) -> User:
    with tenant_context(tenant_id):
        user = User(email=email, password_hash="hash-secret", full_name="Initial")
        session.add(user)
        await session.commit()
    return user


async def _audit_rows(
    session: AsyncSession, tenant_id: uuid.UUID, *, entity_table: str, action: str | None = None
) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.entity_table == entity_table)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    with tenant_context(tenant_id):
        return list((await session.execute(stmt)).scalars().all())


@pytest.fixture(autouse=True)
def _reset_audit_context() -> None:
    """No request middleware runs in these direct-session tests, so seed the audit
    ContextVars to their system defaults (actor/ip/request_id None). Individual tests
    override them explicitly to simulate a request."""
    audit.actor_user_id_ctx.set(None)
    audit.request_id_ctx.set(None)
    audit.request_ip_ctx.set(None)


async def test_insert_of_audited_model_writes_one_insert_row(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    user = await _make_user(db_session, tenant_a)
    rows = await _audit_rows(db_session, tenant_a, entity_table="core_users", action="INSERT")
    assert len(rows) == 1
    row = rows[0]
    assert row.entity_id == str(user.id)
    assert row.tenant_id == tenant_a
    assert row.diff["new"]["email"] == "a@acme.test"
    # password_hash is in User.__audit_exclude__ — never captured, even on insert.
    assert "password_hash" not in row.diff["new"]


async def test_update_writes_row_with_per_field_old_new_diff(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    user = await _make_user(db_session, tenant_a)
    with tenant_context(tenant_a):
        user.full_name = "Renamed"
        await db_session.commit()
    rows = await _audit_rows(db_session, tenant_a, entity_table="core_users", action="UPDATE")
    assert len(rows) == 1
    # Only the changed column appears, with both sides.
    assert rows[0].diff == {"full_name": {"old": "Initial", "new": "Renamed"}}


async def test_delete_writes_row_with_old_values(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    user = await _make_user(db_session, tenant_a)
    with tenant_context(tenant_a):
        await db_session.delete(user)
        await db_session.commit()
    rows = await _audit_rows(db_session, tenant_a, entity_table="core_users", action="DELETE")
    assert len(rows) == 1
    old = rows[0].diff["old"]
    assert old["email"] == "a@acme.test"
    assert "password_hash" not in old


async def test_audit_row_carries_actor_ip_and_request_id_when_context_set(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    actor = uuid.uuid4()
    audit.actor_user_id_ctx.set(actor)
    audit.request_ip_ctx.set("203.0.113.7")
    audit.request_id_ctx.set("req-abc")
    await _make_user(db_session, tenant_a)
    rows = await _audit_rows(db_session, tenant_a, entity_table="core_users", action="INSERT")
    assert rows[0].actor_user_id == actor
    assert rows[0].request_ip == "203.0.113.7"
    assert rows[0].request_id == "req-abc"


async def test_system_write_with_no_actor_still_audits_with_null_actor(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    # The autouse fixture leaves actor/ip/request_id None — a system/unauthenticated write.
    await _make_user(db_session, tenant_a)
    rows = await _audit_rows(db_session, tenant_a, entity_table="core_users", action="INSERT")
    assert len(rows) == 1
    assert rows[0].actor_user_id is None
    assert rows[0].request_id is None
    assert rows[0].request_ip is None


async def test_append_only_update_raises_token_at_db_level(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _make_user(db_session, tenant_a)
    # system_context suspends the D-007 filter so the UPDATE reaches the DB unfiltered —
    # the per-dialect BEFORE UPDATE trigger is what raises the token (migration 0005).
    with system_context(), pytest.raises(IntegrityError) as excinfo:
        await db_session.execute(sa.update(AuditLog).values(action="TAMPERED"))
        await db_session.commit()
    assert "ATLAS_AUDIT_APPEND_ONLY" in str(excinfo.value)
    await db_session.rollback()


async def test_append_only_delete_raises_token_at_db_level(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _make_user(db_session, tenant_a)
    with system_context(), pytest.raises(IntegrityError) as excinfo:
        await db_session.execute(sa.delete(AuditLog))
        await db_session.commit()
    assert "ATLAS_AUDIT_APPEND_ONLY" in str(excinfo.value)
    await db_session.rollback()


def test_translator_maps_append_only_token_to_envelope() -> None:
    # Unit-test the D-014 translator directly: a DBAPIError carrying the token maps to the
    # 409 audit.append_only envelope; an unrelated DB error maps to None (caller -> 500).
    err = IntegrityError("UPDATE ...", {}, Exception("ATLAS_AUDIT_APPEND_ONLY"))
    translated = translate_db_guard_error(err)
    assert isinstance(translated, AtlasError)
    assert translated.status_code == 409
    assert translated.code == "audit.append_only"

    benign = IntegrityError("UNIQUE failed", {}, Exception("UNIQUE constraint failed"))
    assert translate_db_guard_error(benign) is None


async def test_bulk_orm_update_on_audited_model_raises_hard_error(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _make_user(db_session, tenant_a)
    with tenant_context(tenant_a), pytest.raises(AtlasError) as excinfo:
        await db_session.execute(sa.update(User).values(full_name="bulk"))
    assert excinfo.value.code == "audit.bulk_write_forbidden"
    await db_session.rollback()


async def test_bulk_orm_delete_on_audited_model_raises_hard_error(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _make_user(db_session, tenant_a)
    with tenant_context(tenant_a), pytest.raises(AtlasError) as excinfo:
        await db_session.execute(sa.delete(User))
    assert excinfo.value.code == "audit.bulk_write_forbidden"
    await db_session.rollback()


async def test_audit_rows_are_tenant_isolated(
    db_session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await _make_user(db_session, tenant_a, email="a@a.test")
    await _make_user(db_session, tenant_b, email="b@b.test")
    # Tenant A's normal (filtered) read sees only tenant A's audit rows.
    a_rows = await _audit_rows(db_session, tenant_a, entity_table="core_users")
    b_rows = await _audit_rows(db_session, tenant_b, entity_table="core_users")
    assert {row.tenant_id for row in a_rows} == {tenant_a}
    assert {row.tenant_id for row in b_rows} == {tenant_b}
    assert a_rows and b_rows


async def test_rollback_discards_both_change_and_audit_row(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    # Same-transaction atomicity: flush writes the audit row in the SAME transaction, so a
    # rollback after the change persists neither the user nor its audit row.
    with tenant_context(tenant_a):
        user = User(email="ghost@acme.test", password_hash="h", full_name="Ghost")
        db_session.add(user)
        await db_session.flush()  # audit row buffered + written, not yet committed
        ghost_id = user.id
        await db_session.rollback()
    with system_context():
        users = (await db_session.execute(select(User).where(User.id == ghost_id))).all()
        audits = (
            await db_session.execute(
                select(AuditLog).where(AuditLog.entity_id == str(ghost_id))
            )
        ).all()
    assert users == []
    assert audits == []


async def test_commit_persists_both_change_and_audit_row(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    user = await _make_user(db_session, tenant_a, email="kept@acme.test")
    with system_context():
        users = (await db_session.execute(select(User).where(User.id == user.id))).all()
        audits = (
            await db_session.execute(select(AuditLog).where(AuditLog.entity_id == str(user.id)))
        ).all()
    assert len(users) == 1
    assert len(audits) == 1


async def test_append_only_token_surfaces_as_envelope_at_api_level() -> None:
    # End-to-end (D-014): a route raising the trigger token returns the 409 audit.append_only
    # envelope, not a raw 500. A throwaway app keeps the production router untouched.
    app = create_app()

    @app.get("/api/v1/_test/append-only")
    async def _boom() -> None:  # pragma: no cover - body raises before returning
        raise IntegrityError("UPDATE ...", {}, Exception("ATLAS_AUDIT_APPEND_ONLY"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as test_client:
        response = await test_client.get("/api/v1/_test/append-only")
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "audit.append_only"
    assert body["error"]["request_id"] is not None


def test_json_safe_serializes_uuid_decimal_and_datetime() -> None:
    from datetime import datetime
    from decimal import Decimal

    value_id = uuid.uuid4()
    assert json_safe(value_id) == str(value_id)
    assert json_safe(Decimal("1.50")) == "1.50"
    assert json_safe(datetime(2026, 6, 12, 10, 30)) == "2026-06-12T10:30:00"
    assert json_safe(None) is None
    assert json_safe(42) == 42
