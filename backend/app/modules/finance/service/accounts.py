"""Chart-of-accounts business logic (D-021): accounts and the presentation-group tree.

The service layer owns every rule (CLAUDE.md rule 7); the router stays thin.

- accounts: normal_balance defaults from account_type (D-021) so the stored side can never
  disagree with the type; code uniqueness is the DB UNIQUE(tenant_id, code) constraint,
  surfaced here as a ConflictError before the flush would raise.
- account groups: a presentation tree (D-021) with cycle protection — a group can never be
  its own ancestor.

``from __future__ import annotations`` keeps annotations as strings so ``Page[Account]`` (the
ORM model) is never evaluated into a Pydantic schema at import — ``Account`` is a SQLAlchemy
model, not a Pydantic one; the router re-validates the page items into ``AccountRead``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.finance.constants import (
    AccountType,
    CashFlowCategory,
    NormalBalance,
    normal_balance_for,
)
from app.modules.finance.models import Account, AccountGroup
from app.modules.finance.schemas import (
    AccountCreate,
    AccountFilter,
    AccountGroupCreate,
    AccountUpdate,
)


async def _account_by_code(
    session: AsyncSession, tenant_id: uuid.UUID, code: str
) -> Account | None:
    stmt = select(Account).where(Account.tenant_id == tenant_id, Account.code == code)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_account(
    session: AsyncSession, tenant_id: uuid.UUID, account_id: uuid.UUID
) -> Account:
    account = await session.get(Account, account_id)
    if account is None or account.tenant_id != tenant_id:
        raise NotFoundError(message="Account not found", code="finance.account_not_found")
    return account


async def create_account(
    session: AsyncSession, tenant_id: uuid.UUID, payload: AccountCreate
) -> Account:
    """Create a GL account (D-021). Defaults normal_balance from account_type when the
    caller omits it; rejects a duplicate code with a ConflictError (the DB UNIQUE is the
    backstop). Validates that a referenced account group exists in the tenant."""
    if await _account_by_code(session, tenant_id, payload.code) is not None:
        raise ConflictError(
            message=f"An account with code {payload.code} already exists",
            code="finance.account_code_conflict",
            details={"code": payload.code},
        )
    if payload.account_group_id is not None:
        await _require_group(session, tenant_id, payload.account_group_id)

    account_type = AccountType(payload.account_type)
    normal_balance = (
        NormalBalance(payload.normal_balance)
        if payload.normal_balance is not None
        else normal_balance_for(account_type)
    )
    cash_flow = (
        CashFlowCategory(payload.cash_flow_category).value
        if payload.cash_flow_category is not None
        else None
    )
    account = Account(
        tenant_id=tenant_id,
        code=payload.code,
        name=payload.name,
        account_type=account_type.value,
        normal_balance=normal_balance.value,
        is_postable=payload.is_postable,
        cash_flow_category=cash_flow,
        is_cash_equivalent=payload.is_cash_equivalent,
        account_group_id=payload.account_group_id,
        is_active=payload.is_active,
        is_monetary=payload.is_monetary,
        currency_code=payload.currency_code,
    )
    session.add(account)
    await session.flush()
    return account


async def update_account(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    account_id: uuid.UUID,
    payload: AccountUpdate,
) -> Account:
    """Partial update of an account's mutable fields (D-010: mutate the loaded object so the
    audit diff is captured). code and account_type are immutable and absent from the schema."""
    account = await get_account(session, tenant_id, account_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("account_group_id") is not None:
        await _require_group(session, tenant_id, data["account_group_id"])
    if data.get("normal_balance") is not None:
        data["normal_balance"] = NormalBalance(data["normal_balance"]).value
    if data.get("cash_flow_category") is not None:
        data["cash_flow_category"] = CashFlowCategory(data["cash_flow_category"]).value
    for field, value in data.items():
        setattr(account, field, value)
    await session.flush()
    return account


async def list_accounts(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    filters: AccountFilter,
    cursor: str | None,
    limit: int,
) -> Page[Account]:
    """Keyset-paginated account list ordered by code (D-014). Filters narrow the set and are
    folded into the cursor fingerprint so a cursor cannot bleed across filtered views."""
    stmt = select(Account).where(Account.tenant_id == tenant_id)
    if filters.account_type is not None:
        stmt = stmt.where(Account.account_type == AccountType(filters.account_type).value)
    if filters.is_postable is not None:
        stmt = stmt.where(Account.is_postable == filters.is_postable)
    if filters.is_active is not None:
        stmt = stmt.where(Account.is_active == filters.is_active)
    if filters.account_group_id is not None:
        stmt = stmt.where(Account.account_group_id == filters.account_group_id)

    fingerprint = filter_fingerprint(
        filters.account_type,
        filters.is_postable,
        filters.is_active,
        filters.account_group_id,
    )
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(Account.code, SortDirection.ASC)],
        pk=Account.id,
        cursor=cursor,
        limit=limit,
        filters=fingerprint,
    )


# --- Account groups -----------------------------------------------------------


async def _require_group(
    session: AsyncSession, tenant_id: uuid.UUID, group_id: uuid.UUID
) -> AccountGroup:
    group = await session.get(AccountGroup, group_id)
    if group is None or group.tenant_id != tenant_id:
        raise NotFoundError(
            message="Account group not found", code="finance.account_group_not_found"
        )
    return group


async def create_account_group(
    session: AsyncSession, tenant_id: uuid.UUID, payload: AccountGroupCreate
) -> AccountGroup:
    """Create a presentation-hierarchy group (D-021). Validates the parent exists in the
    tenant; a top-level group passes parent_id=None. (A new group has no children yet, so
    no cycle is possible at creation — the cycle guard lives in reparenting below.)"""
    existing = (
        await session.execute(
            select(AccountGroup).where(
                AccountGroup.tenant_id == tenant_id, AccountGroup.code == payload.code
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            message=f"An account group with code {payload.code} already exists",
            code="finance.account_group_code_conflict",
            details={"code": payload.code},
        )
    if payload.parent_id is not None:
        await _require_group(session, tenant_id, payload.parent_id)
    group = AccountGroup(
        tenant_id=tenant_id,
        code=payload.code,
        name=payload.name,
        parent_id=payload.parent_id,
        sort_order=payload.sort_order,
    )
    session.add(group)
    await session.flush()
    return group


async def reparent_account_group(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    group_id: uuid.UUID,
    new_parent_id: uuid.UUID | None,
) -> AccountGroup:
    """Move a group under a new parent, rejecting any move that would create a cycle — a
    group can never be its own ancestor (D-021: the tree must stay a tree)."""
    group = await _require_group(session, tenant_id, group_id)
    if new_parent_id is not None:
        if new_parent_id == group_id:
            raise ValidationFailedError(
                message="A group cannot be its own parent",
                code="finance.account_group_cycle",
            )
        await _require_group(session, tenant_id, new_parent_id)
        await _assert_no_cycle(session, tenant_id, group_id, new_parent_id)
    group.parent_id = new_parent_id
    await session.flush()
    return group


async def _assert_no_cycle(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    group_id: uuid.UUID,
    new_parent_id: uuid.UUID,
) -> None:
    """Raise if making ``group_id`` a child of ``new_parent_id`` would form a cycle: walk
    from new_parent up its parent chain; reaching group_id means group_id is already an
    ancestor of the prospective parent. A visited set bounds a pre-existing malformed tree."""
    current: uuid.UUID | None = new_parent_id
    visited: set[uuid.UUID] = set()
    while current is not None:
        if current == group_id:
            raise ValidationFailedError(
                message="Reparenting would create a cycle in the account-group tree",
                code="finance.account_group_cycle",
            )
        if current in visited:
            break
        visited.add(current)
        parent = await _require_group(session, tenant_id, current)
        current = parent.parent_id


async def list_account_groups(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[AccountGroup]:
    """All groups for the tenant, ordered for stable tree rendering (sort_order then code).
    Groups are a bounded configuration set, so this returns the full list (no pagination)."""
    stmt = (
        select(AccountGroup)
        .where(AccountGroup.tenant_id == tenant_id)
        .order_by(AccountGroup.sort_order, AccountGroup.code)
    )
    return list((await session.execute(stmt)).scalars().all())
