"""Price-list business logic (PLAN 7.1): price-list CRUD + per-list item management.

The service layer owns every rule (CLAUDE.md rule 7); the router stays thin. Rules enforced here:

- ``code`` uniqueness per tenant (friendly ConflictError before the DB UNIQUE backstop);
- ``currency_code`` must exist in finance's catalog (D-029, via
``finance/queries.currency_exists``);
- ``customer_group_id`` (when set) must reference an existing group in the tenant;
- ``valid_to`` (when set) must be >= ``valid_from`` (schema/DB CHECK back it);
- a price-list item's ``item_id`` must exist in inventory (D-029, via
  ``inventory/queries.item_exists``); an item appears at most once per list (friendly ConflictError
  before the UNIQUE backstop); ``unit_price`` / ``min_quantity`` >= 0.

The deterministic best-match RESOLVER is a separate concern in ``price_resolution.py`` (exposed via
``queries.resolve_price``); this file is the maintenance CRUD only. ``from __future__ import
annotations`` keeps ``Page[PriceList]`` a string at import; the router re-validates page items.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import (
    DEFAULT_LIMIT,
    OrderKey,
    SortDirection,
    filter_fingerprint,
    paginate,
)
from app.core.schemas import Page
from app.modules.finance import queries as finance_queries
from app.modules.inventory import queries as inventory_queries
from app.modules.sales.constants import PriceListStatus
from app.modules.sales.models import PriceList, PriceListItem
from app.modules.sales.schemas import (
    PriceListCreate,
    PriceListFilter,
    PriceListItemCreate,
    PriceListUpdate,
)
from app.modules.sales.service.customer_groups import get_customer_group

# --- Price lists --------------------------------------------------------------


async def _price_list_by_code(
    session: AsyncSession, tenant_id: uuid.UUID, code: str
) -> PriceList | None:
    stmt = select(PriceList).where(
        PriceList.tenant_id == tenant_id, PriceList.code == code
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _validate_currency(
    session: AsyncSession, tenant_id: uuid.UUID, currency_code: str
) -> None:
    if not await finance_queries.currency_exists(session, tenant_id, currency_code):
        raise ValidationFailedError(
            message=f"Currency {currency_code} does not exist in the finance catalog",
            code="sales.currency_not_found",
            details={"currency_code": currency_code},
        )


async def get_price_list(
    session: AsyncSession, tenant_id: uuid.UUID, price_list_id: uuid.UUID
) -> PriceList:
    price_list = await session.get(PriceList, price_list_id)
    if price_list is None or price_list.tenant_id != tenant_id:
        raise NotFoundError(
            message="Price list not found", code="sales.price_list_not_found"
        )
    return price_list


async def create_price_list(
    session: AsyncSession, tenant_id: uuid.UUID, payload: PriceListCreate
) -> PriceList:
    """Create a price list (condition header). Rejects a duplicate code; validates the currency
    exists in finance and the targeted group (if any) exists. ``status`` defaults to ACTIVE,
    ``priority`` to 0 (schema)."""
    if await _price_list_by_code(session, tenant_id, payload.code) is not None:
        raise ConflictError(
            message=f"A price list with code {payload.code} already exists",
            code="sales.price_list_code_conflict",
            details={"code": payload.code},
        )
    await _validate_currency(session, tenant_id, payload.currency_code)
    if payload.customer_group_id is not None:
        await get_customer_group(session, tenant_id, payload.customer_group_id)
    price_list = PriceList(
        tenant_id=tenant_id,
        code=payload.code,
        name=payload.name,
        currency_code=payload.currency_code,
        customer_group_id=payload.customer_group_id,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        status=PriceListStatus(payload.status).value,
        priority=payload.priority,
    )
    session.add(price_list)
    await session.flush()
    return price_list


async def update_price_list(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    price_list_id: uuid.UUID,
    payload: PriceListUpdate,
) -> PriceList:
    """Partial update (D-010: mutate the loaded object so the audit diff is captured). ``code`` is
    immutable; a changed currency/group is re-validated; the resulting [valid_from, valid_to] window
    must stay coherent (the DB CHECK is the backstop, but reject early with a friendly error);
    ``status`` may move freely between ACTIVE/INACTIVE."""
    price_list = await get_price_list(session, tenant_id, price_list_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("currency_code") is not None:
        await _validate_currency(session, tenant_id, data["currency_code"])
    if data.get("customer_group_id") is not None:
        await get_customer_group(session, tenant_id, data["customer_group_id"])
    if data.get("status") is not None:
        data["status"] = PriceListStatus(data["status"]).value
    for field, value in data.items():
        setattr(price_list, field, value)
    new_from = price_list.valid_from
    new_to = price_list.valid_to
    if new_to is not None and new_to < new_from:
        raise ValidationFailedError(
            message="valid_to must be on or after valid_from",
            code="sales.price_list_invalid_window",
            details={"valid_from": str(new_from), "valid_to": str(new_to)},
        )
    await session.flush()
    return price_list


async def list_price_lists(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    filters: PriceListFilter,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[PriceList]:
    """Keyset-paginated price-list list ordered by code (D-014). The optional status filter folds
    into the cursor fingerprint."""
    stmt = select(PriceList).where(PriceList.tenant_id == tenant_id)
    if filters.status is not None:
        stmt = stmt.where(PriceList.status == PriceListStatus(filters.status).value)
    fingerprint = filter_fingerprint(filters.status)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(PriceList.code, SortDirection.ASC)],
        pk=PriceList.id,
        cursor=cursor,
        limit=limit,
        filters=fingerprint,
    )


# --- Price-list items (nested under a price list) -----------------------------


async def list_price_list_items(
    session: AsyncSession, tenant_id: uuid.UUID, price_list_id: uuid.UUID
) -> list[PriceListItem]:
    """The price list's items, ordered by creation (PLAN 7.1). 404s if the price list does not exist
    (so a missing list and an empty list are distinguishable)."""
    await get_price_list(session, tenant_id, price_list_id)
    stmt = (
        select(PriceListItem)
        .where(
            PriceListItem.tenant_id == tenant_id,
            PriceListItem.price_list_id == price_list_id,
        )
        .order_by(PriceListItem.created_at, PriceListItem.id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def add_price_list_item(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    price_list_id: uuid.UUID,
    payload: PriceListItemCreate,
) -> PriceListItem:
    """Add a base price for an item to a price list. Validates the list exists, the item exists in
    inventory (D-029, via ``inventory/queries.item_exists`` — no cross-module FK), and the item is
    not already priced on this list (friendly ConflictError before the UNIQUE backstop)."""
    await get_price_list(session, tenant_id, price_list_id)
    if not await inventory_queries.item_exists(session, tenant_id, payload.item_id):
        raise ValidationFailedError(
            message="Referenced inventory item does not exist",
            code="sales.item_not_found",
            details={"item_id": str(payload.item_id)},
        )
    existing = (
        await session.execute(
            select(PriceListItem.id).where(
                PriceListItem.tenant_id == tenant_id,
                PriceListItem.price_list_id == price_list_id,
                PriceListItem.item_id == payload.item_id,
            )
        )
    ).first()
    if existing is not None:
        raise ConflictError(
            message="This item is already priced on the price list",
            code="sales.price_list_item_conflict",
            details={
                "price_list_id": str(price_list_id),
                "item_id": str(payload.item_id),
            },
        )
    item = PriceListItem(
        tenant_id=tenant_id,
        price_list_id=price_list_id,
        item_id=payload.item_id,
        unit_price=payload.unit_price,
        min_quantity=payload.min_quantity,
    )
    session.add(item)
    await session.flush()
    return item


async def remove_price_list_item(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    price_list_id: uuid.UUID,
    item_id: uuid.UUID,
) -> None:
    """Remove an item's price from a list (PLAN 7.1). 404s if the (list, item) price does not exist.
    A hard delete: a price-list item is low-churn config with no document history of its own, so
    removal is a real delete, not a status flip (the procurement approved-item precedent)."""
    stmt = select(PriceListItem).where(
        PriceListItem.tenant_id == tenant_id,
        PriceListItem.price_list_id == price_list_id,
        PriceListItem.item_id == item_id,
    )
    item = (await session.execute(stmt)).scalar_one_or_none()
    if item is None:
        raise NotFoundError(
            message="Price-list item not found",
            code="sales.price_list_item_not_found",
        )
    await session.delete(item)
    await session.flush()
