"""Item-category business logic (PLAN 5.1, D-020/D-029): CRUD + GL-account validation.

The service layer owns every rule (CLAUDE.md rule 7); the router stays thin. Cross-module GL
accounts (D-029): each category account id, when set, must exist in finance — validated through
``finance/queries.account_exists_by_id`` (the sanctioned cross-module read, STRUCTURE §5);
inventory never imports finance models.

``from __future__ import annotations`` keeps annotations as strings so ``Page[ItemCategory]`` (the
ORM model) is never evaluated into a Pydantic schema at import; the router re-validates page items.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, paginate
from app.core.schemas import Page
from app.modules.finance import queries as finance_queries
from app.modules.inventory.constants import CostingMethod
from app.modules.inventory.models import ItemCategory
from app.modules.inventory.schemas import ItemCategoryCreate, ItemCategoryUpdate


async def _category_by_code(
    session: AsyncSession, tenant_id: uuid.UUID, code: str
) -> ItemCategory | None:
    stmt = select(ItemCategory).where(
        ItemCategory.tenant_id == tenant_id, ItemCategory.code == code
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_category(
    session: AsyncSession, tenant_id: uuid.UUID, category_id: uuid.UUID
) -> ItemCategory:
    category = await session.get(ItemCategory, category_id)
    if category is None or category.tenant_id != tenant_id:
        raise NotFoundError(
            message="Item category not found", code="inventory.category_not_found"
        )
    return category


async def _validate_category_accounts(
    session: AsyncSession, tenant_id: uuid.UUID, account_ids: list[uuid.UUID | None]
) -> None:
    """Each supplied GL-account id must exist in finance (D-029): validated through the finance
    queries contract, never a cross-module FK. None ids are skipped (accounts are optional)."""
    for account_id in account_ids:
        if account_id is None:
            continue
        if not await finance_queries.account_exists_by_id(session, tenant_id, account_id):
            raise ValidationFailedError(
                message="Referenced GL account does not exist",
                code="inventory.gl_account_not_found",
                details={"account_id": str(account_id)},
            )


async def create_category(
    session: AsyncSession, tenant_id: uuid.UUID, payload: ItemCategoryCreate
) -> ItemCategory:
    """Create an item category (D-020/D-029). Rejects a duplicate code; validates each supplied GL
    account exists in finance."""
    if await _category_by_code(session, tenant_id, payload.code) is not None:
        raise ConflictError(
            message=f"An item category with code {payload.code} already exists",
            code="inventory.category_code_conflict",
            details={"code": payload.code},
        )
    await _validate_category_accounts(
        session,
        tenant_id,
        [
            payload.inventory_account_id,
            payload.cogs_account_id,
            payload.price_difference_account_id,
        ],
    )
    category = ItemCategory(
        tenant_id=tenant_id,
        code=payload.code,
        name=payload.name,
        default_costing_method=CostingMethod(payload.default_costing_method).value,
        inventory_account_id=payload.inventory_account_id,
        cogs_account_id=payload.cogs_account_id,
        price_difference_account_id=payload.price_difference_account_id,
    )
    session.add(category)
    await session.flush()
    return category


async def update_category(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    category_id: uuid.UUID,
    payload: ItemCategoryUpdate,
) -> ItemCategory:
    """Partial update of a category (D-010: mutate the loaded object so the audit diff is captured).
    code is immutable and absent from the schema; changed GL accounts are re-validated."""
    category = await get_category(session, tenant_id, category_id)
    data = payload.model_dump(exclude_unset=True)
    await _validate_category_accounts(
        session,
        tenant_id,
        [
            data.get(key)
            for key in (
                "inventory_account_id",
                "cogs_account_id",
                "price_difference_account_id",
            )
        ],
    )
    if data.get("default_costing_method") is not None:
        data["default_costing_method"] = CostingMethod(data["default_costing_method"]).value
    for field, value in data.items():
        setattr(category, field, value)
    await session.flush()
    return category


async def list_categories(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[ItemCategory]:
    """Keyset-paginated categories ordered by code (D-014)."""
    stmt = select(ItemCategory).where(ItemCategory.tenant_id == tenant_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(ItemCategory.code, SortDirection.ASC)],
        pk=ItemCategory.id,
        cursor=cursor,
        limit=limit,
    )
