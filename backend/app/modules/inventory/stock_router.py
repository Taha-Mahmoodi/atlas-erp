"""Inventory stock HTTP layer (PLAN 5.2), included into the inventory router.

Split out of router.py (which covers the 5.1 item-master reference endpoints) the same way
finance's journal_router/ap_router are: mounted via ``router.include_router(stock_router)`` so the
module stays ONE surface at ``/api/v1/inventory`` — no second mount in main.py. Covers warehouses,
bins, the stock-move ledger and the on-hand projection.

Permission-guarded (D-009): warehouse/bin read vs manage; move read vs create. Writes commit
through ``run_in_uow`` (D-011) so audit rides the transaction. The move-creating endpoints (create
+ reverse) are IDEMPOTENT (D-013): they POST a stock document that changes on-hand, so a retried
request must not double-move — ``capture()`` lands in the same uow as the move so document + replay
record commit atomically.

Warehouses + bins are slow-changing reference data, so their lists support conditional GETs via a
collection ETag (PERFORMANCE §3 / D-035). The move ledger and the on-hand projection are
transactional/fast-changing, so they carry NO ETag (the journal-entry precedent).
"""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, Request, Response

from app.core.conditional import collection_etag, conditional_response, request_fingerprint
from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.inventory import service
from app.modules.inventory.constants import (
    INVENTORY_BIN_MANAGE,
    INVENTORY_BIN_READ,
    INVENTORY_MOVE_CREATE,
    INVENTORY_MOVE_READ,
    INVENTORY_WAREHOUSE_MANAGE,
    INVENTORY_WAREHOUSE_READ,
)
from app.modules.inventory.models import Bin, Warehouse
from app.modules.inventory.schemas import (
    BinCreate,
    BinRead,
    BinUpdate,
    StockMoveCreate,
    StockMoveFilter,
    StockMoveRead,
    StockOnHandRead,
    WarehouseCreate,
    WarehouseRead,
    WarehouseUpdate,
)

stock_router = APIRouter(tags=["inventory-stock"])

CursorParamsDep = Depends(cursor_params)
# Module-level Depends singletons (ruff B008): the D-013 reservation guard per move endpoint.
_CreateMoveIdempotentDep = Depends(Idempotent("inventory.stock_move.create"))
_ReverseMoveIdempotentDep = Depends(Idempotent("inventory.stock_move.reverse"))


async def _commit[T](session: SessionDep, work: Callable[[], Awaitable[T]]) -> T:
    """Run a service call inside the D-011 uow, returning its ORM result refreshed in the async
    context so a sync ``model_validate`` never trips MissingGreenlet (twin of router._commit)."""
    holder: list[T] = []

    async def _work() -> None:
        result = await work()
        await session.refresh(result)
        holder.append(result)

    await run_in_uow(session, _work)
    return holder[0]


# --- Warehouses ---------------------------------------------------------------


@stock_router.get(
    "/warehouses",
    response_model=Page[WarehouseRead],
    dependencies=[Depends(require_permission(INVENTORY_WAREHOUSE_READ))],
)
async def list_warehouses(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
) -> Page[WarehouseRead] | Response:
    """Conditional-GET supported (D-035): collection ETag over the warehouse reference list."""
    fingerprint = request_fingerprint(params.cursor, params.limit)
    etag = await collection_etag(session, Warehouse, request_fingerprint=fingerprint)

    async def builder() -> Page[WarehouseRead]:
        page = await service.list_warehouses(
            session, current.tenant_id, cursor=params.cursor, limit=params.limit
        )
        return map_page(page, WarehouseRead)

    return await conditional_response(request, response, etag, builder)


@stock_router.post(
    "/warehouses",
    response_model=WarehouseRead,
    status_code=201,
    dependencies=[Depends(require_permission(INVENTORY_WAREHOUSE_MANAGE))],
)
async def create_warehouse(
    payload: WarehouseCreate, current: CurrentUserDep, session: SessionDep
) -> WarehouseRead:
    warehouse = await _commit(
        session, lambda: service.create_warehouse(session, current.tenant_id, payload)
    )
    return WarehouseRead.model_validate(warehouse)


@stock_router.get(
    "/warehouses/{warehouse_id}",
    response_model=WarehouseRead,
    dependencies=[Depends(require_permission(INVENTORY_WAREHOUSE_READ))],
)
async def get_warehouse(
    warehouse_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> WarehouseRead:
    warehouse = await service.get_warehouse(session, current.tenant_id, warehouse_id)
    return WarehouseRead.model_validate(warehouse)


@stock_router.patch(
    "/warehouses/{warehouse_id}",
    response_model=WarehouseRead,
    dependencies=[Depends(require_permission(INVENTORY_WAREHOUSE_MANAGE))],
)
async def update_warehouse(
    warehouse_id: uuid.UUID,
    payload: WarehouseUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> WarehouseRead:
    warehouse = await _commit(
        session,
        lambda: service.update_warehouse(session, current.tenant_id, warehouse_id, payload),
    )
    return WarehouseRead.model_validate(warehouse)


# --- Bins ---------------------------------------------------------------------


@stock_router.get(
    "/bins",
    response_model=Page[BinRead],
    dependencies=[Depends(require_permission(INVENTORY_BIN_READ))],
)
async def list_bins(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    warehouse_id: uuid.UUID | None = None,
) -> Page[BinRead] | Response:
    """Conditional-GET supported (D-035): collection ETag over the bin reference list; the
    warehouse filter folds into the request fingerprint so a filtered 304 is correct."""
    fingerprint = request_fingerprint(params.cursor, params.limit, warehouse_id)
    etag = await collection_etag(session, Bin, request_fingerprint=fingerprint)

    async def builder() -> Page[BinRead]:
        page = await service.list_bins(
            session,
            current.tenant_id,
            warehouse_id=warehouse_id,
            cursor=params.cursor,
            limit=params.limit,
        )
        return map_page(page, BinRead)

    return await conditional_response(request, response, etag, builder)


@stock_router.post(
    "/bins",
    response_model=BinRead,
    status_code=201,
    dependencies=[Depends(require_permission(INVENTORY_BIN_MANAGE))],
)
async def create_bin(
    payload: BinCreate, current: CurrentUserDep, session: SessionDep
) -> BinRead:
    bin_row = await _commit(
        session, lambda: service.create_bin(session, current.tenant_id, payload)
    )
    return BinRead.model_validate(bin_row)


@stock_router.get(
    "/bins/{bin_id}",
    response_model=BinRead,
    dependencies=[Depends(require_permission(INVENTORY_BIN_READ))],
)
async def get_bin(
    bin_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> BinRead:
    bin_row = await service.get_bin(session, current.tenant_id, bin_id)
    return BinRead.model_validate(bin_row)


@stock_router.patch(
    "/bins/{bin_id}",
    response_model=BinRead,
    dependencies=[Depends(require_permission(INVENTORY_BIN_MANAGE))],
)
async def update_bin(
    bin_id: uuid.UUID, payload: BinUpdate, current: CurrentUserDep, session: SessionDep
) -> BinRead:
    bin_row = await _commit(
        session, lambda: service.update_bin(session, current.tenant_id, bin_id, payload)
    )
    return BinRead.model_validate(bin_row)


# --- Stock moves --------------------------------------------------------------


@stock_router.post(
    "/stock-moves",
    response_model=StockMoveRead,
    status_code=201,
    dependencies=[Depends(require_permission(INVENTORY_MOVE_CREATE))],
)
async def create_stock_move(
    payload: StockMoveCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _CreateMoveIdempotentDep,
) -> StockMoveRead:
    """Create + POST a stock move (PLAN 5.2). IDEMPOTENT (D-013): the move changes on-hand, so a
    retried request must not double-move — capture() lands in the same uow as the move."""
    holder: dict[str, StockMoveRead] = {}

    async def work() -> None:
        move = await service.create_move(session, current.tenant_id, payload)
        await session.refresh(move)
        holder["read"] = await idem.capture(
            StockMoveRead.model_validate(move), status_code=201
        )

    await run_in_uow(session, work)
    return holder["read"]


@stock_router.post(
    "/stock-moves/{move_id}/reverse",
    response_model=StockMoveRead,
    status_code=201,
    dependencies=[Depends(require_permission(INVENTORY_MOVE_CREATE))],
)
async def reverse_stock_move(
    move_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _ReverseMoveIdempotentDep,
) -> StockMoveRead:
    """Reverse a posted move by posting the OPPOSITE move (PLAN 5.2); returns the NEW reversing
    move. IDEMPOTENT (D-013): it posts a stock document, so a retry must not double-reverse."""
    holder: dict[str, StockMoveRead] = {}

    async def work() -> None:
        reversal = await service.reverse_move(session, current.tenant_id, move_id)
        await session.refresh(reversal)
        holder["read"] = await idem.capture(
            StockMoveRead.model_validate(reversal), status_code=201
        )

    await run_in_uow(session, work)
    return holder["read"]


@stock_router.get(
    "/stock-moves",
    response_model=Page[StockMoveRead],
    dependencies=[Depends(require_permission(INVENTORY_MOVE_READ))],
)
async def list_stock_moves(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    item_id: uuid.UUID | None = None,
    bin_id: uuid.UUID | None = None,
    move_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> Page[StockMoveRead]:
    """The move ledger (PLAN 5.2): keyset-paginated, filtered by item/bin/type/date range. No ETag
    (transactional/fast-changing, the journal-entry precedent)."""
    filters = StockMoveFilter(
        item_id=item_id,
        bin_id=bin_id,
        move_type=move_type,
        date_from=date_from,
        date_to=date_to,
    )
    page = await service.list_moves(
        session, current.tenant_id, filters=filters, cursor=params.cursor, limit=params.limit
    )
    return map_page(page, StockMoveRead)


@stock_router.get(
    "/stock-moves/{move_id}",
    response_model=StockMoveRead,
    dependencies=[Depends(require_permission(INVENTORY_MOVE_READ))],
)
async def get_stock_move(
    move_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> StockMoveRead:
    move = await service.get_move(session, current.tenant_id, move_id)
    return StockMoveRead.model_validate(move)


# --- On-hand projection -------------------------------------------------------


@stock_router.get(
    "/stock-on-hand",
    response_model=Page[StockOnHandRead],
    dependencies=[Depends(require_permission(INVENTORY_MOVE_READ))],
)
async def list_stock_on_hand(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    item_id: uuid.UUID | None = None,
    bin_id: uuid.UUID | None = None,
) -> Page[StockOnHandRead]:
    """The on-hand projection (PLAN 5.2, D-036): keyset-paginated quant rows, optionally by item
    and/or bin. The maintained projection of the move ledger — an indexed read, not a SUM over
    history. No ETag (changes with every move)."""
    page = await service.list_on_hand(
        session,
        current.tenant_id,
        item_id=item_id,
        bin_id=bin_id,
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, StockOnHandRead)
