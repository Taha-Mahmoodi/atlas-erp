"""Non-bypassable tenancy enforcement (D-007), proven through real sessions on the
migrated template database against Tenant + TenantSetting."""

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import TenancyError
from app.core.models import Base, RefreshSession, TenantMixin, tenant_fk, tenant_unique
from app.core.tenancy import get_current_tenant_id, system_context, tenant_context
from app.modules.admin.models import TenantSetting
from app.modules.admin.service import provision_user

# Mapper enumeration per D-007: every current AND future TenantMixin model is
# auto-covered by the parametrized guard tests below.
TENANT_SCOPED_MODELS = sorted(
    (mapper.class_ for mapper in Base.registry.mappers if issubclass(mapper.class_, TenantMixin)),
    key=lambda cls: cls.__name__,
)


async def _seed_setting(
    session: AsyncSession, tenant_id: uuid.UUID, key: str, value: dict
) -> uuid.UUID:
    with tenant_context(tenant_id):
        setting = TenantSetting(key=key, value=value)
        session.add(setting)
        await session.commit()
    return setting.id


@pytest.fixture
async def seeded_settings(
    db_session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> dict[str, list[uuid.UUID]]:
    return {
        "a": [
            await _seed_setting(db_session, tenant_a, "theme", {"mode": "dark"}),
            await _seed_setting(db_session, tenant_a, "locale", {"lang": "en"}),
        ],
        "b": [await _seed_setting(db_session, tenant_b, "theme", {"mode": "light"})],
    }


async def test_bare_select_under_tenant_a_returns_zero_tenant_b_rows(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    seeded_settings: dict[str, list[uuid.UUID]],
) -> None:
    with tenant_context(tenant_a):
        rows = (await db_session.execute(select(TenantSetting))).scalars().all()
    assert len(rows) == len(seeded_settings["a"])
    assert all(row.tenant_id == tenant_a for row in rows)


async def _seed_session(session: AsyncSession, tenant_id: uuid.UUID, email: str) -> uuid.UUID:
    # The ORM-bulk-update/delete D-007 tests target RefreshSession on purpose: it is the
    # one TenantMixin model that is NOT audited (high-churn token state, D-010), so the
    # audit bulk-write guard does not fire and the tenancy NARROWING of bulk ORM writes
    # stays provable. Audited models reject bulk writes outright (see test_audit.py).
    now = datetime.now(UTC)
    with system_context():
        user = await provision_user(session, tenant_id, email=email, password="pw-correct")
        refresh = RefreshSession(
            tenant_id=tenant_id,
            user_id=user.id,
            current_jti_hash="0" * 64,
            issued_at=now,
            last_used_at=now,
            expires_at=now,
        )
        session.add(refresh)
        await session.commit()
    return refresh.id


@pytest.fixture
async def seeded_sessions(
    db_session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> dict[str, uuid.UUID]:
    return {
        "a": await _seed_session(db_session, tenant_a, "a@sess.test"),
        "b": await _seed_session(db_session, tenant_b, "b@sess.test"),
    }


async def test_orm_update_without_where_touches_only_tenant_a_rows(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    seeded_sessions: dict[str, uuid.UUID],
) -> None:
    with tenant_context(tenant_a):
        await db_session.execute(sa.update(RefreshSession).values(user_agent="touched"))
        await db_session.commit()
    with system_context():
        rows = (await db_session.execute(select(RefreshSession))).scalars().all()
    assert all(row.user_agent == "touched" for row in rows if row.tenant_id == tenant_a)
    assert all(row.user_agent != "touched" for row in rows if row.tenant_id == tenant_b)


async def test_orm_delete_without_where_touches_only_tenant_a_rows(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    seeded_sessions: dict[str, uuid.UUID],
) -> None:
    with tenant_context(tenant_a):
        await db_session.execute(sa.delete(RefreshSession))
        await db_session.commit()
    with system_context():
        remaining = (await db_session.execute(select(RefreshSession))).scalars().all()
    assert [row.tenant_id for row in remaining] == [tenant_b]


async def test_execution_with_unset_contextvar_raises(db_session: AsyncSession) -> None:
    with pytest.raises(TenancyError) as excinfo:
        await db_session.execute(select(TenantSetting))
    assert excinfo.value.code == "tenancy.context_missing"


async def test_insert_carrying_foreign_tenant_id_raises(
    db_session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        db_session.add(TenantSetting(tenant_id=tenant_b, key="theme", value={}))
        with pytest.raises(TenancyError) as excinfo:
            await db_session.flush()
    assert excinfo.value.code == "tenancy.tenant_mismatch"
    await db_session.rollback()


async def test_system_context_bypasses_filtering(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    seeded_settings: dict[str, list[uuid.UUID]],
) -> None:
    with system_context():
        rows = (await db_session.execute(select(TenantSetting))).scalars().all()
    assert {row.tenant_id for row in rows} == {tenant_a, tenant_b}


async def test_same_statement_under_two_tenants_returns_each_tenants_rows(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    seeded_settings: dict[str, list[uuid.UUID]],
) -> None:
    # Pins track_closure_variables=False: ONE statement object, two executions.
    statement = select(TenantSetting)
    with tenant_context(tenant_a):
        rows_a = (await db_session.execute(statement)).scalars().all()
    with tenant_context(tenant_b):
        rows_b = (await db_session.execute(statement)).scalars().all()
    assert {row.tenant_id for row in rows_a} == {tenant_a}
    assert {row.tenant_id for row in rows_b} == {tenant_b}


async def test_new_instance_without_tenant_id_gets_stamped_from_context(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        setting = TenantSetting(key="theme", value={"mode": "dark"})
        db_session.add(setting)
        await db_session.commit()
    assert setting.tenant_id == tenant_a


async def test_unknown_tenant_id_fails_fk_even_under_system_context(
    db_session: AsyncSession,
) -> None:
    # Proves the D-007 backstop end to end: PRAGMA foreign_keys=ON + the
    # tenant_fk anchor to adm_tenants reject ghosts the listeners let through.
    with system_context():
        db_session.add(TenantSetting(tenant_id=uuid.uuid4(), key="theme", value={}))
        with pytest.raises(IntegrityError):
            await db_session.flush()
    await db_session.rollback()


async def test_session_get_under_tenant_a_returns_none_for_tenant_b_row(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    seeded_settings: dict[str, list[uuid.UUID]],
) -> None:
    b_id = seeded_settings["b"][0]
    # Identity-map hits skip SQL (benign per D-007: request sessions are never
    # shared across tenants); expunge to force the filtered SELECT path.
    db_session.expunge_all()
    with tenant_context(tenant_a):
        assert await db_session.get(TenantSetting, b_id) is None
    with tenant_context(tenant_b):
        found = await db_session.get(TenantSetting, b_id)
    assert found is not None and found.tenant_id == tenant_b


def test_get_current_tenant_id_fail_closed_and_context_accessors() -> None:
    with pytest.raises(TenancyError):
        get_current_tenant_id()
    tenant_id = uuid.uuid4()
    with tenant_context(tenant_id):
        assert get_current_tenant_id() == tenant_id
    with system_context():
        assert get_current_tenant_id() is None


def test_tenant_fk_builds_root_anchor_and_composite_forms() -> None:
    root = tenant_fk("adm_tenants")
    assert root.column_keys == ["tenant_id"]
    assert [element.target_fullname for element in root.elements] == ["adm_tenants.id"]
    composite = tenant_fk("inv_items", "item_id")
    assert composite.column_keys == ["tenant_id", "item_id"]
    assert [element.target_fullname for element in composite.elements] == [
        "inv_items.tenant_id",
        "inv_items.id",
    ]


def test_tenant_unique_builds_composite_unique_constraint() -> None:
    metadata = sa.MetaData()
    table = sa.Table(
        "x_parents",
        metadata,
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("tenant_id", sa.Uuid, nullable=False),
        tenant_unique(),
    )
    constraint = next(c for c in table.constraints if isinstance(c, sa.UniqueConstraint))
    assert [column.name for column in constraint.columns] == ["tenant_id", "id"]


def test_modules_contain_no_raw_sql_or_core_inserts() -> None:
    """The D-007 grep gate: Core statements (`text(`, Core `.insert(`) bypass the
    ORM filter, so they are banned under app/modules/ — core/ and tests/ are exempt."""
    modules_dir = Path(__file__).resolve().parents[2] / "app" / "modules"
    banned = re.compile(r"\btext\s*\(|\.insert\s*\(")
    offenders = [
        f"{path.relative_to(modules_dir)}:{lineno}"
        for path in sorted(modules_dir.rglob("*.py"))
        for lineno, line in enumerate(path.read_text().splitlines(), start=1)
        if banned.search(line)
    ]
    assert offenders == []


@pytest.mark.parametrize("model", TENANT_SCOPED_MODELS, ids=lambda cls: cls.__name__)
class TestEveryTenantScopedMapper:
    """D-007 mapper-enumeration guard: extends automatically to every future
    TenantMixin model registered on Base."""

    def test_has_indexed_not_null_tenant_id_column(self, model: type[TenantMixin]) -> None:
        table = model.__table__  # type: ignore[attr-defined]
        column = table.columns["tenant_id"]
        assert column.nullable is False
        assert any("tenant_id" in index.columns for index in table.indexes)

    async def test_select_fail_closed_without_context(
        self, model: type[TenantMixin], db_session: AsyncSession
    ) -> None:
        with pytest.raises(TenancyError):
            await db_session.execute(select(model))

    async def test_select_under_tenant_a_filters_to_tenant_a(
        self,
        model: type[TenantMixin],
        db_session: AsyncSession,
        tenant_a: uuid.UUID,
        tenant_b: uuid.UUID,
        seeded_settings: dict[str, list[uuid.UUID]],
    ) -> None:
        with tenant_context(tenant_a):
            rows = (await db_session.execute(select(model))).scalars().all()
        assert all(row.tenant_id == tenant_a for row in rows)
