"""Account-group hierarchy rules (D-021): parent validation and cycle rejection."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.finance import service
from app.modules.finance.schemas import AccountGroupCreate


async def test_create_group_tree(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    with tenant_context(tenant_a):
        root = await service.create_account_group(
            db_session, tenant_a, AccountGroupCreate(code="A", name="Assets")
        )
        child = await service.create_account_group(
            db_session,
            tenant_a,
            AccountGroupCreate(code="A1", name="Current Assets", parent_id=root.id),
        )
        await db_session.commit()
    assert child.parent_id == root.id


async def test_duplicate_group_code_raises_conflict(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        await service.create_account_group(
            db_session, tenant_a, AccountGroupCreate(code="A", name="Assets")
        )
        await db_session.commit()
        with pytest.raises(ConflictError):
            await service.create_account_group(
                db_session, tenant_a, AccountGroupCreate(code="A", name="Dup")
            )


async def test_create_group_with_unknown_parent_raises_not_found(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a), pytest.raises(NotFoundError):
        await service.create_account_group(
            db_session,
            tenant_a,
            AccountGroupCreate(code="A1", name="x", parent_id=uuid.uuid4()),
        )


async def test_reparent_into_descendant_is_rejected_as_cycle(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        root = await service.create_account_group(
            db_session, tenant_a, AccountGroupCreate(code="A", name="Assets")
        )
        child = await service.create_account_group(
            db_session, tenant_a, AccountGroupCreate(code="A1", name="Current", parent_id=root.id)
        )
        await db_session.commit()
        # Making the root a child of its own descendant would close a cycle.
        with pytest.raises(ValidationFailedError) as excinfo:
            await service.reparent_account_group(db_session, tenant_a, root.id, child.id)
    assert excinfo.value.code == "finance.account_group_cycle"


async def test_reparent_to_self_is_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        group = await service.create_account_group(
            db_session, tenant_a, AccountGroupCreate(code="A", name="Assets")
        )
        await db_session.commit()
        with pytest.raises(ValidationFailedError) as excinfo:
            await service.reparent_account_group(db_session, tenant_a, group.id, group.id)
    assert excinfo.value.code == "finance.account_group_cycle"


async def test_reparent_to_valid_parent_succeeds(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        a = await service.create_account_group(
            db_session, tenant_a, AccountGroupCreate(code="A", name="Assets")
        )
        b = await service.create_account_group(
            db_session, tenant_a, AccountGroupCreate(code="B", name="Liabilities")
        )
        await db_session.commit()
        moved = await service.reparent_account_group(db_session, tenant_a, b.id, a.id)
    assert moved.parent_id == a.id
