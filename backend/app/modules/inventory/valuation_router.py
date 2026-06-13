"""Inventory valuation HTTP layer (PLAN 5.3), included into the inventory router.

A sibling sub-router (the finance journal_router/ap_router precedent), mounted via
``router.include_router(valuation_router)`` so the module stays ONE surface at
``/api/v1/inventory``. Exposes the moving-average valuation projection and the FIFO drill-down —
both read the
maintained value SSOT (D-020/D-037), guarded by ``inventory.valuation.read`` (D-009). No ETag: the
valuation/layers change with every valued move (the journal-entry precedent). PERFORMANCE §6:
index-served, within the ≤3-query budget.
"""

import uuid

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.inventory import service
from app.modules.inventory.constants import INVENTORY_VALUATION_READ
from app.modules.inventory.schemas import CostLayerRead, StockValuationRead

valuation_router = APIRouter(tags=["inventory-valuation"])

CursorParamsDep = Depends(cursor_params)


@valuation_router.get(
    "/stock-valuations",
    response_model=Page[StockValuationRead],
    dependencies=[Depends(require_permission(INVENTORY_VALUATION_READ))],
)
async def list_stock_valuations(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    item_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
) -> Page[StockValuationRead]:
    """The moving-average valuation projection (PLAN 5.3, D-020/D-037): keyset-paginated per (item,
    warehouse) value + qty + avg cost, optionally by item and/or warehouse. The inventory-value
    dashboard reads this. No ETag (changes with every valued move)."""
    page = await service.list_valuations(
        session,
        current.tenant_id,
        item_id=item_id,
        warehouse_id=warehouse_id,
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, StockValuationRead)


@valuation_router.get(
    "/items/{item_id}/cost-layers",
    response_model=Page[CostLayerRead],
    dependencies=[Depends(require_permission(INVENTORY_VALUATION_READ))],
)
async def list_item_cost_layers(
    item_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    warehouse_id: uuid.UUID | None = None,
    include_exhausted: bool = False,
) -> Page[CostLayerRead]:
    """The FIFO cost layers for an item (PLAN 5.3, D-020): keyset-paginated oldest-first
    (consumption order), live layers by default (``include_exhausted`` widens to fully-consumed).
    The cost-layer drill-down for a FIFO item. No ETag (changes with every move)."""
    page = await service.list_cost_layers(
        session,
        current.tenant_id,
        item_id,
        warehouse_id=warehouse_id,
        include_exhausted=include_exhausted,
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, CostLayerRead)
