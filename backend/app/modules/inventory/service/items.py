"""Item business logic (PLAN 5.1, D-020): CRUD + type/tracking/costing validation.

Rules enforced here: item_code uniqueness (friendly ConflictError before the DB UNIQUE would
raise); category + base UoM exist; costing_method defaults from the category when omitted (D-020),
stored on the item; tracking only on STOCKED items. ``from __future__ import annotations`` keeps
``Page[Item]`` (the ORM model) a string at import; the router re-validates page items.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.inventory.constants import CostingMethod, ItemType, TrackingMode
from app.modules.inventory.models import Item
from app.modules.inventory.schemas import ItemCreate, ItemFilter, ItemUpdate
from app.modules.inventory.service.categories import get_category
from app.modules.inventory.service.uoms import get_uom


def _resolve_tracking(item_type: ItemType, tracking_mode: TrackingMode) -> None:
    """Enforce "tracking only on STOCKED items" (D-020): a NON_STOCKED/SERVICE item must keep
    tracking_mode = NONE — those types carry no stock to track."""
    if item_type != ItemType.STOCKED and tracking_mode != TrackingMode.NONE:
        raise ValidationFailedError(
            message="Only stocked items can be lot- or serial-tracked",
            code="inventory.tracking_requires_stocked",
            details={"item_type": item_type.value, "tracking_mode": tracking_mode.value},
        )


async def get_item(session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID) -> Item:
    item = await session.get(Item, item_id)
    if item is None or item.tenant_id != tenant_id:
        raise NotFoundError(message="Item not found", code="inventory.item_not_found")
    return item


async def create_item(
    session: AsyncSession, tenant_id: uuid.UUID, payload: ItemCreate
) -> Item:
    """Create an item. Validates the category + base UoM exist, defaults costing_method from the
    category when omitted (D-020), and enforces tracking-only-on-stocked. Duplicate item_code →
    ConflictError (the DB UNIQUE is the backstop)."""
    existing = (
        await session.execute(
            select(Item.id).where(
                Item.tenant_id == tenant_id, Item.item_code == payload.item_code
            )
        )
    ).first()
    if existing is not None:
        raise ConflictError(
            message=f"An item with code {payload.item_code} already exists",
            code="inventory.item_code_conflict",
            details={"item_code": payload.item_code},
        )
    category = await get_category(session, tenant_id, payload.category_id)
    await get_uom(session, tenant_id, payload.base_uom_id)

    item_type = ItemType(payload.item_type)
    tracking_mode = TrackingMode(payload.tracking_mode)
    _resolve_tracking(item_type, tracking_mode)
    costing_method = (
        CostingMethod(payload.costing_method)
        if payload.costing_method is not None
        else CostingMethod(category.default_costing_method)
    )
    item = Item(
        tenant_id=tenant_id,
        item_code=payload.item_code,
        name=payload.name,
        description=payload.description,
        item_type=item_type.value,
        category_id=payload.category_id,
        base_uom_id=payload.base_uom_id,
        costing_method=costing_method.value,
        tracking_mode=tracking_mode.value,
        is_active=payload.is_active,
        reorder_point=payload.reorder_point,
        reorder_quantity=payload.reorder_quantity,
    )
    session.add(item)
    await session.flush()
    return item


async def update_item(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID, payload: ItemUpdate
) -> Item:
    """Partial update of an item (D-010: mutate the loaded object). item_code and item_type are
    immutable and absent from the schema; a changed category/base UoM is re-validated and a changed
    tracking_mode is re-checked against the (immutable) item_type."""
    item = await get_item(session, tenant_id, item_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("category_id") is not None:
        await get_category(session, tenant_id, data["category_id"])
    if data.get("base_uom_id") is not None:
        await get_uom(session, tenant_id, data["base_uom_id"])
    if data.get("tracking_mode") is not None:
        _resolve_tracking(ItemType(item.item_type), TrackingMode(data["tracking_mode"]))
        data["tracking_mode"] = TrackingMode(data["tracking_mode"]).value
    if data.get("costing_method") is not None:
        data["costing_method"] = CostingMethod(data["costing_method"]).value
    for field, value in data.items():
        setattr(item, field, value)
    await session.flush()
    return item


async def list_items(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    filters: ItemFilter,
    cursor: str | None,
    limit: int,
) -> Page[Item]:
    """Keyset-paginated item list ordered by item_code (D-014). Filters (type/category/active)
    narrow the set and fold into the cursor fingerprint so a cursor cannot bleed across views."""
    stmt = select(Item).where(Item.tenant_id == tenant_id)
    if filters.item_type is not None:
        stmt = stmt.where(Item.item_type == ItemType(filters.item_type).value)
    if filters.category_id is not None:
        stmt = stmt.where(Item.category_id == filters.category_id)
    if filters.is_active is not None:
        stmt = stmt.where(Item.is_active == filters.is_active)

    fingerprint = filter_fingerprint(
        filters.item_type, filters.category_id, filters.is_active
    )
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(Item.item_code, SortDirection.ASC)],
        pk=Item.id,
        cursor=cursor,
        limit=limit,
        filters=fingerprint,
    )
