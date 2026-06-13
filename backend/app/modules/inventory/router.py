"""Inventory HTTP layer (thin): parse -> call service -> return schema (PLAN 5.1 + 5.2).

REST under ``/api/v1/inventory``: item-categories, uoms, items (CRUD + filtered list) and the
per-item uom-conversions nested resource (5.1); the warehouse/bin/stock-move/on-hand surface (5.2)
lives in the sibling ``stock_router`` mounted at the foot of this file. Every route is guarded by an
inventory permission key (D-009). Writes commit through ``run_in_uow`` (D-011) so audit rows ride
the same transaction; results are validated into their Read schema AFTER the uow commits.

The slow-changing reference lists (item-categories, uoms, items) support conditional GETs via a
tenant-scoped collection ETag (PERFORMANCE §3 / D-035): an If-None-Match hit returns 304 without
running the page query. Items are semi-reference data (they change less than transactions), so the
items list carries an ETag too — its filters are folded into the request fingerprint so a filtered
304 is correct.
"""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, Request, Response

from app.core.conditional import collection_etag, conditional_response, request_fingerprint
from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.inventory import service
from app.modules.inventory.constants import (
    INVENTORY_CATEGORY_MANAGE,
    INVENTORY_CATEGORY_READ,
    INVENTORY_ITEM_MANAGE,
    INVENTORY_ITEM_READ,
    INVENTORY_UOM_MANAGE,
    INVENTORY_UOM_READ,
)
from app.modules.inventory.models import Item, ItemCategory, Uom
from app.modules.inventory.schemas import (
    ItemCategoryCreate,
    ItemCategoryRead,
    ItemCategoryUpdate,
    ItemCreate,
    ItemFilter,
    ItemRead,
    ItemUpdate,
    UomConversionCreate,
    UomConversionRead,
    UomCreate,
    UomRead,
    UomUpdate,
)
from app.modules.inventory.stock_router import stock_router

router = APIRouter(prefix="/api/v1/inventory", tags=["inventory"])
CursorParamsDep = Depends(cursor_params)


async def _commit[T](session: SessionDep, work: Callable[[], Awaitable[T]]) -> T:
    """Run a service call inside the D-011 uow, returning its ORM result refreshed in the async
    context so a sync ``model_validate`` never trips MissingGreenlet (twin of finance _commit)."""
    holder: list[T] = []

    async def _work() -> None:
        result = await work()
        await session.refresh(result)
        holder.append(result)

    await run_in_uow(session, _work)
    return holder[0]


# --- Item categories ----------------------------------------------------------


@router.get(
    "/item-categories",
    response_model=Page[ItemCategoryRead],
    dependencies=[Depends(require_permission(INVENTORY_CATEGORY_READ))],
)
async def list_item_categories(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
) -> Page[ItemCategoryRead] | Response:
    """Conditional-GET supported (D-035): collection ETag over the item-category reference list."""
    fingerprint = request_fingerprint(params.cursor, params.limit)
    etag = await collection_etag(session, ItemCategory, request_fingerprint=fingerprint)

    async def builder() -> Page[ItemCategoryRead]:
        page = await service.list_categories(
            session, current.tenant_id, cursor=params.cursor, limit=params.limit
        )
        return map_page(page, ItemCategoryRead)

    return await conditional_response(request, response, etag, builder)


@router.post(
    "/item-categories",
    response_model=ItemCategoryRead,
    status_code=201,
    dependencies=[Depends(require_permission(INVENTORY_CATEGORY_MANAGE))],
)
async def create_item_category(
    payload: ItemCategoryCreate, current: CurrentUserDep, session: SessionDep
) -> ItemCategoryRead:
    category = await _commit(
        session, lambda: service.create_category(session, current.tenant_id, payload)
    )
    return ItemCategoryRead.model_validate(category)


@router.get(
    "/item-categories/{category_id}",
    response_model=ItemCategoryRead,
    dependencies=[Depends(require_permission(INVENTORY_CATEGORY_READ))],
)
async def get_item_category(
    category_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> ItemCategoryRead:
    category = await service.get_category(session, current.tenant_id, category_id)
    return ItemCategoryRead.model_validate(category)


@router.patch(
    "/item-categories/{category_id}",
    response_model=ItemCategoryRead,
    dependencies=[Depends(require_permission(INVENTORY_CATEGORY_MANAGE))],
)
async def update_item_category(
    category_id: uuid.UUID,
    payload: ItemCategoryUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> ItemCategoryRead:
    category = await _commit(
        session,
        lambda: service.update_category(session, current.tenant_id, category_id, payload),
    )
    return ItemCategoryRead.model_validate(category)


# --- Units of measure ---------------------------------------------------------


@router.get(
    "/uoms",
    response_model=Page[UomRead],
    dependencies=[Depends(require_permission(INVENTORY_UOM_READ))],
)
async def list_uoms(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
) -> Page[UomRead] | Response:
    """Conditional-GET supported (D-035): collection ETag over the unit-of-measure list."""
    fingerprint = request_fingerprint(params.cursor, params.limit)
    etag = await collection_etag(session, Uom, request_fingerprint=fingerprint)

    async def builder() -> Page[UomRead]:
        page = await service.list_uoms(
            session, current.tenant_id, cursor=params.cursor, limit=params.limit
        )
        return map_page(page, UomRead)

    return await conditional_response(request, response, etag, builder)


@router.post(
    "/uoms",
    response_model=UomRead,
    status_code=201,
    dependencies=[Depends(require_permission(INVENTORY_UOM_MANAGE))],
)
async def create_uom(
    payload: UomCreate, current: CurrentUserDep, session: SessionDep
) -> UomRead:
    uom = await _commit(session, lambda: service.create_uom(session, current.tenant_id, payload))
    return UomRead.model_validate(uom)


@router.get(
    "/uoms/{uom_id}",
    response_model=UomRead,
    dependencies=[Depends(require_permission(INVENTORY_UOM_READ))],
)
async def get_uom(
    uom_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> UomRead:
    uom = await service.get_uom(session, current.tenant_id, uom_id)
    return UomRead.model_validate(uom)


@router.patch(
    "/uoms/{uom_id}",
    response_model=UomRead,
    dependencies=[Depends(require_permission(INVENTORY_UOM_MANAGE))],
)
async def update_uom(
    uom_id: uuid.UUID, payload: UomUpdate, current: CurrentUserDep, session: SessionDep
) -> UomRead:
    uom = await _commit(
        session, lambda: service.update_uom(session, current.tenant_id, uom_id, payload)
    )
    return UomRead.model_validate(uom)


# --- Items --------------------------------------------------------------------


@router.get(
    "/items",
    response_model=Page[ItemRead],
    dependencies=[Depends(require_permission(INVENTORY_ITEM_READ))],
)
async def list_items(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    item_type: str | None = None,
    category_id: uuid.UUID | None = None,
    is_active: bool | None = None,
) -> Page[ItemRead] | Response:
    """Conditional-GET supported (D-035): items are semi-reference data, so the collection ETag
    covers the visible item set; the type/category/active filters fold into the request fingerprint
    so a filtered 304 is correct."""
    filters = ItemFilter(item_type=item_type, category_id=category_id, is_active=is_active)
    fingerprint = request_fingerprint(
        params.cursor, params.limit, item_type, category_id, is_active
    )
    etag = await collection_etag(session, Item, request_fingerprint=fingerprint)

    async def builder() -> Page[ItemRead]:
        page = await service.list_items(
            session, current.tenant_id, filters=filters, cursor=params.cursor, limit=params.limit
        )
        return map_page(page, ItemRead)

    return await conditional_response(request, response, etag, builder)


@router.post(
    "/items",
    response_model=ItemRead,
    status_code=201,
    dependencies=[Depends(require_permission(INVENTORY_ITEM_MANAGE))],
)
async def create_item(
    payload: ItemCreate, current: CurrentUserDep, session: SessionDep
) -> ItemRead:
    item = await _commit(session, lambda: service.create_item(session, current.tenant_id, payload))
    return ItemRead.model_validate(item)


@router.get(
    "/items/{item_id}",
    response_model=ItemRead,
    dependencies=[Depends(require_permission(INVENTORY_ITEM_READ))],
)
async def get_item(
    item_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> ItemRead:
    item = await service.get_item(session, current.tenant_id, item_id)
    return ItemRead.model_validate(item)


@router.patch(
    "/items/{item_id}",
    response_model=ItemRead,
    dependencies=[Depends(require_permission(INVENTORY_ITEM_MANAGE))],
)
async def update_item(
    item_id: uuid.UUID, payload: ItemUpdate, current: CurrentUserDep, session: SessionDep
) -> ItemRead:
    item = await _commit(
        session, lambda: service.update_item(session, current.tenant_id, item_id, payload)
    )
    return ItemRead.model_validate(item)


# --- Per-item UoM conversions (nested) ----------------------------------------


@router.get(
    "/items/{item_id}/uom-conversions",
    response_model=list[UomConversionRead],
    dependencies=[Depends(require_permission(INVENTORY_ITEM_READ))],
)
async def list_item_conversions(
    item_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> list[UomConversionRead]:
    conversions = await service.list_conversions(session, current.tenant_id, item_id)
    return [UomConversionRead.model_validate(conversion) for conversion in conversions]


@router.post(
    "/items/{item_id}/uom-conversions",
    response_model=UomConversionRead,
    status_code=201,
    dependencies=[Depends(require_permission(INVENTORY_ITEM_MANAGE))],
)
async def create_item_conversion(
    item_id: uuid.UUID,
    payload: UomConversionCreate,
    current: CurrentUserDep,
    session: SessionDep,
) -> UomConversionRead:
    conversion = await _commit(
        session, lambda: service.create_conversion(session, current.tenant_id, item_id, payload)
    )
    return UomConversionRead.model_validate(conversion)


# PLAN 5.2 stock surface (warehouses, bins, moves, on-hand) is a sibling sub-router mounted here, so
# the whole module stays ONE surface at /api/v1/inventory — the finance journal_router/ap_router
# include precedent (no second mount in main.py).
router.include_router(stock_router)
