"""Account service rules (D-021): CRUD, unique code, normal_balance derivation, pagination."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.tenancy import tenant_context
from app.modules.finance import service
from app.modules.finance.constants import AccountType, NormalBalance
from app.modules.finance.schemas import AccountCreate, AccountFilter, AccountUpdate


async def test_create_account_persists_and_reads_back(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        created = await service.create_account(
            db_session,
            tenant_a,
            AccountCreate(code="1000", name="Cash", account_type=AccountType.ASSET),
        )
        await db_session.commit()
        fetched = await service.get_account(db_session, tenant_a, created.id)
    assert fetched.code == "1000"
    assert fetched.name == "Cash"
    assert fetched.account_type == AccountType.ASSET.value


@pytest.mark.parametrize(
    ("account_type", "expected"),
    [
        (AccountType.ASSET, NormalBalance.DEBIT),
        (AccountType.EXPENSE, NormalBalance.DEBIT),
        (AccountType.LIABILITY, NormalBalance.CREDIT),
        (AccountType.EQUITY, NormalBalance.CREDIT),
        (AccountType.REVENUE, NormalBalance.CREDIT),
    ],
)
async def test_normal_balance_defaults_from_account_type(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    account_type: AccountType,
    expected: NormalBalance,
) -> None:
    with tenant_context(tenant_a):
        account = await service.create_account(
            db_session,
            tenant_a,
            AccountCreate(code=f"X-{account_type.value}", name="x", account_type=account_type),
        )
    assert account.normal_balance == expected.value


async def test_duplicate_code_raises_conflict(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        await service.create_account(
            db_session,
            tenant_a,
            AccountCreate(code="1000", name="Cash", account_type=AccountType.ASSET),
        )
        await db_session.commit()
        with pytest.raises(ConflictError) as excinfo:
            await service.create_account(
                db_session,
                tenant_a,
                AccountCreate(code="1000", name="Other", account_type=AccountType.ASSET),
            )
    assert excinfo.value.code == "finance.account_code_conflict"


async def test_update_account_changes_mutable_fields(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        account = await service.create_account(
            db_session,
            tenant_a,
            AccountCreate(code="1000", name="Cash", account_type=AccountType.ASSET),
        )
        await db_session.commit()
        updated = await service.update_account(
            db_session,
            tenant_a,
            account.id,
            AccountUpdate(name="Cash and Equivalents", is_active=False),
        )
    assert updated.name == "Cash and Equivalents"
    assert updated.is_active is False


async def test_get_unknown_account_raises_not_found(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a), pytest.raises(NotFoundError):
        await service.get_account(db_session, tenant_a, uuid.uuid4())


async def test_create_account_with_unknown_group_raises_not_found(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a), pytest.raises(NotFoundError):
        await service.create_account(
            db_session,
            tenant_a,
            AccountCreate(
                code="1000",
                name="Cash",
                account_type=AccountType.ASSET,
                account_group_id=uuid.uuid4(),
            ),
        )


async def test_list_accounts_paginates_by_code(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        for i in range(7):
            await service.create_account(
                db_session,
                tenant_a,
                AccountCreate(
                    code=f"{1000 + i}", name=f"acct {i}", account_type=AccountType.ASSET
                ),
            )
        await db_session.commit()

        seen: list[str] = []
        cursor: str | None = None
        while True:
            page = await service.list_accounts(
                db_session,
                tenant_a,
                filters=AccountFilter(),
                cursor=cursor,
                limit=3,
            )
            seen.extend(account.code for account in page.items)
            if page.next_cursor is None:
                break
            cursor = page.next_cursor

    assert seen == [f"{1000 + i}" for i in range(7)]  # ascending by code, no dupes/gaps


async def test_list_accounts_filters_by_type(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        await service.create_account(
            db_session,
            tenant_a,
            AccountCreate(code="1000", name="Cash", account_type=AccountType.ASSET),
        )
        await service.create_account(
            db_session,
            tenant_a,
            AccountCreate(code="4000", name="Sales", account_type=AccountType.REVENUE),
        )
        await db_session.commit()
        page = await service.list_accounts(
            db_session,
            tenant_a,
            filters=AccountFilter(account_type=AccountType.REVENUE),
            cursor=None,
            limit=50,
        )
    assert [a.code for a in page.items] == ["4000"]
