"""The MRP run engine (PLAN 8.3, D-049, parity PP MRP = PARTIAL): the deterministic, set-based,
level-ordered planning pass that nets demand against supply and writes planned orders.

THE MODEL (D-049):

- **Demand** per item = open sales-order demand (Σ ordered − delivered over CONFIRMED /
  PARTIALLY_DELIVERED sales orders, via ``sales/queries.committed_quantity``) + reorder-point
  shortfall (an item at/below its reorder point demands ``reorder_quantity``, via
  ``inventory/queries.items_below_reorder_point``). These are the LEVEL-0 (independent) demands.
- **Supply** per item = on-hand (``inventory/queries.total_on_hand``) + un-finished open production
  orders (``manufacturing/queries.open_production_order_supply``) + open-incoming POs
  (``procurement/queries.open_incoming_quantity``) + still-open FIRMED/CONVERTED planned orders
  (``manufacturing/queries.planned_make_supply`` — the regeneration policy keeps committed
  proposals as supply).
- **Net requirement** = max(0, demand − supply).
- **MAKE vs BUY** is STRUCTURAL: an item with an ACTIVE default BOM is MAKE (produced in-house, its
  BOM is EXPLODED into dependent component demand); an item with no active BOM is BUY (a leaf the
  explosion stops at — a planned BUY order).
- **The explosion is LEVEL-ORDERED**: level 0 (independently-demanded items) is netted first; each
  MAKE item's net requirement EXPLODES its BOM into dependent demand for its components at the next
  level, accumulating across all parents (a component used by two finished goods sums). Each level
  is processed set-based (the level's items' BOMs/components are batched), capped at
  ``MRP_MAX_EXPLOSION_LEVELS`` so a (masters-rejected-but-defensive) cycle terminates.

BULK / SET-BASED (PERFORMANCE §2): per level the engine issues a BOUNDED number of queries — it
batches the level's active BOMs (ONE query), their components (ONE query), then per item resolves
demand/supply through the cross-module queries (each item-level read is one query, but the NUMBER of
levels is capped and the per-item cross-module reads are the same shape the ATP/reorder paths use —
no per-component N+1 inside a level's explosion). The planned orders are written with ONE bulk
insert; the run header + regeneration delete are O(1).

EXECUTION (PERFORMANCE §3, D-049): the run scans every planning-relevant item, so it is ALWAYS a
``manufacturing.mrp_run`` BACKGROUND JOB — the endpoint submits the job and returns 202 {job_id};
the handler here calls :func:`run_mrp`. The rough capacity check (``mrp_capacity.py``) runs as part
of the same job after the plan is written.

Conversion (firm/convert/cancel) + the run/planned-order reads live in ``planned_orders.py``; the
capacity check in ``mrp_capacity.py``. ``service/__init__`` re-exports all three.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.jobs import register_job
from app.core.numbering import claim_number, ensure_sequence
from app.modules.inventory import queries as inventory_queries
from app.modules.manufacturing import queries as mfg_queries
from app.modules.manufacturing.constants import (
    MRP_DEFAULT_HORIZON_DAYS,
    MRP_MAX_EXPLOSION_LEVELS,
    MRP_RUN_DOC_TYPE,
    MRP_RUN_JOB,
    MRP_RUN_NUMBER_PADDING,
    MRP_RUN_NUMBER_PREFIX,
    MRP_RUN_SEQUENCE_NAME,
    BomStatus,
    MrpRunStatus,
    PlannedOrderStatus,
    PlannedOrderType,
)
from app.modules.manufacturing.models import Bom, BomComponent, MrpRun, PlannedOrder
from app.modules.manufacturing.service.mrp_capacity import rough_capacity_check
from app.modules.procurement import queries as procurement_queries
from app.modules.sales import queries as sales_queries

_QUANTITY_DP = Decimal(1).scaleb(-6)


def _quantize_qty(value: Decimal) -> Decimal:
    return value.quantize(_QUANTITY_DP, rounding=ROUND_HALF_UP)


@dataclass
class _PlanLine:
    """One accumulated planned-order line being built (an item's net requirement at a level)."""

    item_id: uuid.UUID
    order_type: str
    quantity: Decimal
    level: int
    source_notes: str


async def _gather_independent_demand(
    session: AsyncSession, tenant_id: uuid.UUID
) -> dict[uuid.UUID, Decimal]:
    """Level-0 (independent) demand per item: open sales-order demand + reorder-point shortfall
    (module docstring). Returns ``{item_id: total_demand}``. Two set-based reads (the reorder scan +
    the open-sales-demand items) plus one ``committed_quantity`` per demanded item — the same shape
    sales ATP uses, no per-line N+1 inside."""
    demand: dict[uuid.UUID, Decimal] = {}

    # Reorder-point shortfall: each below-reorder item demands its reorder_quantity (the 6.4 scan's
    # source) — ONE set-based query.
    below = await inventory_queries.items_below_reorder_point(session, tenant_id)
    for item_id, _on_hand, _rp, reorder_quantity in below:
        demand[item_id] = demand.get(item_id, Decimal(0)) + Decimal(str(reorder_quantity))

    # Open sales-order demand: the items with undelivered confirmed sales-order lines, each summed
    # via committed_quantity (the ATP reservation source). One query to find the items, then the
    # committed sum per item (the sales-module-owned read).
    for item_id, qty in (await _open_sales_demand_items(session, tenant_id)).items():
        demand[item_id] = demand.get(item_id, Decimal(0)) + qty
    return demand


async def _open_sales_demand_items(
    session: AsyncSession, tenant_id: uuid.UUID
) -> dict[uuid.UUID, Decimal]:
    """The items carrying open sales-order demand + the committed quantity per item (PLAN 8.3).
    Reads the SALES module: first the distinct items on undelivered confirmed order lines (one
    query through sales/queries), then ``committed_quantity`` per item (the canonical reservation
    sum). Bounded: one discovery query + one committed read per demanded item (the small set)."""
    item_ids = await sales_queries.open_demand_item_ids(session, tenant_id)
    result: dict[uuid.UUID, Decimal] = {}
    for item_id in item_ids:
        qty = await sales_queries.committed_quantity(session, tenant_id, item_id)
        if qty > 0:
            result[item_id] = qty
    return result


async def _net_supply(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> Decimal:
    """The total SUPPLY of an item (module docstring): on-hand + un-finished open production
    orders + open-incoming POs + still-open FIRMED/CONVERTED planned orders. Four bounded
    cross-module reads (no N+1), summed exact (D-015)."""
    on_hand = Decimal(str(await inventory_queries.total_on_hand(session, tenant_id, item_id)))
    production = await mfg_queries.open_production_order_supply(session, tenant_id, item_id)
    on_order = Decimal(
        str(await procurement_queries.open_incoming_quantity(session, tenant_id, item_id))
    )
    firmed = await mfg_queries.planned_make_supply(session, tenant_id, item_id)
    return on_hand + production + on_order + firmed


async def _active_boms_for(
    session: AsyncSession, tenant_id: uuid.UUID, item_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Bom]:
    """The ACTIVE default BOMs for a BATCH of items (PLAN 8.3) — ONE query (the level's MAKE-vs-BUY
    test + explosion input), keyed by item_id. An item absent from the result is BUY (no active
    BOM)."""
    if not item_ids:
        return {}
    stmt = select(Bom).where(
        Bom.tenant_id == tenant_id,
        Bom.item_id.in_(item_ids),
        Bom.status == BomStatus.ACTIVE.value,
        Bom.is_default.is_(True),
    )
    return {bom.item_id: bom for bom in (await session.execute(stmt)).scalars().all()}


async def _components_for(
    session: AsyncSession, tenant_id: uuid.UUID, bom_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[BomComponent]]:
    """The components of a BATCH of BOMs (PLAN 8.3) — ONE query, grouped by bom_id (the level's
    explosion input, no per-BOM N+1)."""
    if not bom_ids:
        return {}
    stmt = (
        select(BomComponent)
        .where(BomComponent.tenant_id == tenant_id, BomComponent.bom_id.in_(bom_ids))
        .order_by(BomComponent.line_number)
    )
    grouped: dict[uuid.UUID, list[BomComponent]] = {}
    for component in (await session.execute(stmt)).scalars().all():
        grouped.setdefault(component.bom_id, []).append(component)
    return grouped


def _explode(
    bom: Bom, components: list[BomComponent], parent_net: Decimal
) -> dict[uuid.UUID, Decimal]:
    """Dependent component demand from making ``parent_net`` units of a BOM's parent (PLAN 8.3):
    per component, ``quantity_per × parent_net / base_quantity × (1 + scrap_percent/100)``,
    quantized — the create_production_order explosion math. Returns
    ``{component_item_id: dependent_demand}`` (summed when a component repeats)."""
    base_quantity = Decimal(str(bom.base_quantity))
    out: dict[uuid.UUID, Decimal] = {}
    for component in components:
        scrap_factor = Decimal(1) + (Decimal(str(component.scrap_percent)) / Decimal(100))
        dependent = _quantize_qty(
            (Decimal(str(component.quantity_per)) * parent_net / base_quantity) * scrap_factor
        )
        if dependent > 0:
            out[component.component_item_id] = out.get(
                component.component_item_id, Decimal(0)
            ) + dependent
    return out


async def _plan_levels(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[_PlanLine]:
    """Net demand against supply LEVEL BY LEVEL, exploding MAKE items (module docstring). Returns
    the accumulated planned-order lines. Level 0 is the independent demand; each subsequent level
    is the dependent demand the prior level's MAKE explosions raised, capped at
    ``MRP_MAX_EXPLOSION_LEVELS`` (cycle guard). Per level the BOM lookups are batched (two
    queries); the per-item demand/supply reads reuse the bounded cross-module queries (no N+1)."""
    lines: list[_PlanLine] = []
    # The current level's GROSS demand per item (independent at level 0, dependent thereafter).
    pending: dict[uuid.UUID, Decimal] = await _gather_independent_demand(session, tenant_id)
    # Items already netted in an EARLIER level — the cycle/diamond guard: a component re-appearing
    # at a deeper level is folded into its earlier net rather than re-planned (low-level-code).
    netted: set[uuid.UUID] = set()
    level = 0

    while pending and level < MRP_MAX_EXPLOSION_LEVELS:
        item_ids = [item_id for item_id in pending if item_id not in netted]
        if not item_ids:
            break
        boms = await _active_boms_for(session, tenant_id, item_ids)
        components_by_bom = await _components_for(
            session, tenant_id, [bom.id for bom in boms.values()]
        )
        next_pending: dict[uuid.UUID, Decimal] = {}
        for item_id in item_ids:
            gross = pending[item_id]
            supply = await _net_supply(session, tenant_id, item_id)
            net = gross - supply
            netted.add(item_id)
            if net <= 0:
                continue  # supply covers it — no planned order, no dependent demand
            net = _quantize_qty(net)
            bom = boms.get(item_id)
            order_type = (
                PlannedOrderType.MAKE.value if bom is not None else PlannedOrderType.BUY.value
            )
            lines.append(
                _PlanLine(
                    item_id=item_id,
                    order_type=order_type,
                    quantity=net,
                    level=level,
                    source_notes=f"net {net} = demand {_quantize_qty(gross)} - supply "
                    f"{_quantize_qty(supply)}",
                )
            )
            if bom is not None:
                for component_id, dependent in _explode(
                    bom, components_by_bom.get(bom.id, []), net
                ).items():
                    next_pending[component_id] = (
                        next_pending.get(component_id, Decimal(0)) + dependent
                    )
        pending = next_pending
        level += 1
    return lines


async def _regenerate(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Delete the tenant's prior PLANNED (un-firmed) planned orders before writing a fresh plan (the
    regeneration policy, D-049): a re-run supersedes un-committed proposals. FIRMED / CONVERTED /
    CANCELLED rows survive (FIRMED/CONVERTED net as supply via ``planned_make_supply``). ONE
    set-based DELETE."""
    await session.execute(
        delete(PlannedOrder).where(
            PlannedOrder.tenant_id == tenant_id,
            PlannedOrder.status == PlannedOrderStatus.PLANNED.value,
        )
    )


async def _create_run(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    run_date: date,
    horizon_days: int,
    warehouse_id: uuid.UUID | None,
) -> MrpRun:
    """Register the run document, claim its gapless MRP- number, persist the RUNNING run row (D-012,
    the depreciation-run precedent)."""
    run_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        MRP_RUN_DOC_TYPE,
        run_id,
        doc_number=None,
        status=MrpRunStatus.RUNNING.value,
    )
    await ensure_sequence(
        session,
        tenant_id,
        MRP_RUN_SEQUENCE_NAME,
        MRP_RUN_NUMBER_PREFIX,
        MRP_RUN_NUMBER_PADDING,
        year_reset=True,
    )
    run_number = await claim_number(session, tenant_id, MRP_RUN_SEQUENCE_NAME, on_date=run_date)
    run = MrpRun(
        id=run_id,
        tenant_id=tenant_id,
        document_id=document.id,
        run_number=run_number,
        status=MrpRunStatus.RUNNING.value,
        run_date=run_date,
        horizon_days=horizon_days,
        warehouse_id=warehouse_id,
        demand_source="sales-order demand + reorder points",
    )
    session.add(run)
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, document.id, doc_number=run_number, status=MrpRunStatus.RUNNING.value
    )
    return run


async def run_mrp(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    run_date: date,
    *,
    horizon_days: int = MRP_DEFAULT_HORIZON_DAYS,
    warehouse_id: uuid.UUID | None = None,
) -> MrpRun:
    """Execute one deterministic MRP run (module docstring): regenerate un-firmed planned orders,
    net demand against supply level by level (exploding MAKE items' BOMs), bulk-write the fresh
    planned orders, then run the rough capacity check — all in the caller's uow (the job's). Returns
    the COMPLETED run. Caller commits via uow (D-011)."""
    run = await _create_run(session, tenant_id, run_date, horizon_days, warehouse_id)
    await _regenerate(session, tenant_id)
    lines = await _plan_levels(session, tenant_id)

    rows: list[dict[str, Any]] = []
    make_count = 0
    buy_count = 0
    for line in lines:
        if line.order_type == PlannedOrderType.MAKE.value:
            make_count += 1
        else:
            buy_count += 1
        rows.append(
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "mrp_run_id": run.id,
                "item_id": line.item_id,
                "order_type": line.order_type,
                "quantity": line.quantity,
                "due_date": run_date,
                "status": PlannedOrderStatus.PLANNED.value,
                "source_notes": line.source_notes,
                "level": line.level,
                "converted_document_id": None,
            }
        )
    if rows:
        await session.execute(insert(PlannedOrder), rows)

    await rough_capacity_check(session, tenant_id, run.id, horizon_days)

    run.status = MrpRunStatus.COMPLETED.value
    run.planned_make_count = make_count
    run.planned_buy_count = buy_count
    run.completed_at = datetime.now(UTC)
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, run.document_id, status=MrpRunStatus.COMPLETED.value
    )
    return run


@register_job(MRP_RUN_JOB)
async def mrp_run_job(
    session: AsyncSession, tenant_id: uuid.UUID, payload: dict[str, Any]
) -> dict[str, Any]:
    """Background-job handler (PERFORMANCE §3, D-049): the MRP run ALWAYS executes as a job and the
    endpoint returns 202 {job_id}. Delegates to :func:`run_mrp`."""
    run = await run_mrp(
        session,
        tenant_id,
        date.fromisoformat(payload["run_date"]),
        horizon_days=int(payload.get("horizon_days", MRP_DEFAULT_HORIZON_DAYS)),
        warehouse_id=(
            uuid.UUID(payload["warehouse_id"]) if payload.get("warehouse_id") else None
        ),
    )
    await session.refresh(run)
    return {
        "run_id": str(run.id),
        "run_number": run.run_number,
        "planned_make_count": run.planned_make_count,
        "planned_buy_count": run.planned_buy_count,
    }
