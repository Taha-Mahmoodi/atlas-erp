"""Sales pricing HTTP layer (PLAN 7.1): price-list CRUD, the nested price-list-items sub-resource,
and the price-quote resolver endpoint.

A sibling router under the same ``/api/v1/sales`` prefix, mounted by ``router.include_router`` in
router.py (the procurement ap_router/sub-router precedent — ONE module surface, no second mount in
main.py). Split from router.py to keep each file under the 400-line cap.

Every route is guarded by a sales pricing permission key (D-009; manage vs read distinct). Writes
commit through ``run_in_uow`` (D-011) so audit rows ride the same transaction. The price-list list
is
slow-changing reference data, so it supports conditional GETs via a tenant-scoped collection ETag
(PERFORMANCE §3 / D-035). The price-quote endpoint is a READ surface over the resolver — useful for
the UI and a testable surface for the deterministic resolution.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.conditional import collection_etag, conditional_response, request_fingerprint
from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.sales import service
from app.modules.sales.constants import (
    SALES_PRICELIST_MANAGE,
    SALES_PRICELIST_READ,
)
from app.modules.sales.models import PriceList
from app.modules.sales.schemas import (
    PriceListCreate,
    PriceListFilter,
    PriceListItemCreate,
    PriceListItemRead,
    PriceListRead,
    PriceListUpdate,
    PriceQuoteRead,
)

# No prefix here: this sub-router is included by router.py under the parent's /api/v1/sales prefix
# (the procurement sub-router precedent — declaring the prefix here would double it).
pricing_router = APIRouter(tags=["sales-pricing"])
CursorParamsDep = Depends(cursor_params)


async def _commit[T](session: SessionDep, work: Callable[[], Awaitable[T]]) -> T:
    """Run a service call inside the D-011 uow, returning its ORM result refreshed in the async
    context so a sync ``model_validate`` never trips MissingGreenlet (the procurement _commit
    twin)."""
    holder: list[T] = []

    async def _work() -> None:
        result = await work()
        await session.refresh(result)
        holder.append(result)

    await run_in_uow(session, _work)
    return holder[0]


# --- Price lists --------------------------------------------------------------


@pricing_router.get(
    "/price-lists",
    response_model=Page[PriceListRead],
    dependencies=[Depends(require_permission(SALES_PRICELIST_READ))],
)
async def list_price_lists(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    status: str | None = None,
) -> Page[PriceListRead] | Response:
    """Conditional-GET supported (D-035): collection ETag over the price-list reference list; the
    status filter folds into the request fingerprint so a filtered 304 is correct."""
    filters = PriceListFilter(status=status)
    fingerprint = request_fingerprint(params.cursor, params.limit, status)
    etag = await collection_etag(session, PriceList, request_fingerprint=fingerprint)

    async def builder() -> Page[PriceListRead]:
        page = await service.list_price_lists(
            session, current.tenant_id, filters=filters, cursor=params.cursor, limit=params.limit
        )
        return map_page(page, PriceListRead)

    return await conditional_response(request, response, etag, builder)


@pricing_router.post(
    "/price-lists",
    response_model=PriceListRead,
    status_code=201,
    dependencies=[Depends(require_permission(SALES_PRICELIST_MANAGE))],
)
async def create_price_list(
    payload: PriceListCreate, current: CurrentUserDep, session: SessionDep
) -> PriceListRead:
    price_list = await _commit(
        session, lambda: service.create_price_list(session, current.tenant_id, payload)
    )
    return PriceListRead.model_validate(price_list)


@pricing_router.get(
    "/price-lists/{price_list_id}",
    response_model=PriceListRead,
    dependencies=[Depends(require_permission(SALES_PRICELIST_READ))],
)
async def get_price_list(
    price_list_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> PriceListRead:
    price_list = await service.get_price_list(session, current.tenant_id, price_list_id)
    return PriceListRead.model_validate(price_list)


@pricing_router.patch(
    "/price-lists/{price_list_id}",
    response_model=PriceListRead,
    dependencies=[Depends(require_permission(SALES_PRICELIST_MANAGE))],
)
async def update_price_list(
    price_list_id: uuid.UUID,
    payload: PriceListUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> PriceListRead:
    price_list = await _commit(
        session,
        lambda: service.update_price_list(session, current.tenant_id, price_list_id, payload),
    )
    return PriceListRead.model_validate(price_list)


# --- Price-list items (nested under a price list) -----------------------------


@pricing_router.get(
    "/price-lists/{price_list_id}/items",
    response_model=list[PriceListItemRead],
    dependencies=[Depends(require_permission(SALES_PRICELIST_READ))],
)
async def list_price_list_items(
    price_list_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> list[PriceListItemRead]:
    items = await service.list_price_list_items(session, current.tenant_id, price_list_id)
    return [PriceListItemRead.model_validate(row) for row in items]


@pricing_router.post(
    "/price-lists/{price_list_id}/items",
    response_model=PriceListItemRead,
    status_code=201,
    dependencies=[Depends(require_permission(SALES_PRICELIST_MANAGE))],
)
async def add_price_list_item(
    price_list_id: uuid.UUID,
    payload: PriceListItemCreate,
    current: CurrentUserDep,
    session: SessionDep,
) -> PriceListItemRead:
    item = await _commit(
        session,
        lambda: service.add_price_list_item(
            session, current.tenant_id, price_list_id, payload
        ),
    )
    return PriceListItemRead.model_validate(item)


@pricing_router.delete(
    "/price-lists/{price_list_id}/items/{item_id}",
    status_code=204,
    dependencies=[Depends(require_permission(SALES_PRICELIST_MANAGE))],
)
async def remove_price_list_item(
    price_list_id: uuid.UUID,
    item_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
) -> Response:
    async def _work() -> None:
        await service.remove_price_list_item(
            session, current.tenant_id, price_list_id, item_id
        )

    await run_in_uow(session, _work)
    return Response(status_code=204)


# --- Price quote (the resolved price) -----------------------------------------


@pricing_router.get(
    "/price-quote",
    response_model=PriceQuoteRead,
    dependencies=[Depends(require_permission(SALES_PRICELIST_READ))],
)
async def get_price_quote(
    current: CurrentUserDep,
    session: SessionDep,
    item_id: Annotated[uuid.UUID, Query()],
    customer_id: Annotated[uuid.UUID, Query()],
    quantity: Annotated[Decimal, Query(gt=0)],
    quote_date: Annotated[date | None, Query(alias="date")] = None,
) -> PriceQuoteRead:
    """Resolve the base unit price for an item + customer + date + quantity (PLAN 7.1, D-043). The
    currency is the customer's default currency (the order line's currency in 7.2). ``date``
    defaults
    to today when omitted. Returns ``matched=False`` (price fields NULL) when no ACTIVE price list
    applies — the UI then prompts for a manual price. A read-only surface over the resolver; no
    discount applied (base price only)."""
    on_date = quote_date if quote_date is not None else date.today()
    # Resolve the customer (404 if unknown) to read its default currency — the currency a 7.2 order
    # line for this customer would carry, which the price list must match.
    customer = await service.get_customer(session, current.tenant_id, customer_id)
    resolved = await service.resolve_price(
        session,
        current.tenant_id,
        item_id=item_id,
        customer_id=customer_id,
        on_date=on_date,
        quantity=quantity,
        currency=customer.default_currency_code,
    )
    return PriceQuoteRead(
        matched=resolved.matched,
        item_id=item_id,
        customer_id=customer_id,
        quote_date=on_date,
        quantity=quantity,
        currency_code=resolved.currency_code,
        unit_price=resolved.unit_price,
        price_list_id=resolved.price_list_id,
        price_list_code=resolved.price_list_code,
    )
