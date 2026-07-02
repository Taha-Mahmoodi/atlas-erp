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
    """Net demand against supply in LOW-LEVEL-CODE order, exploding MAKE items (module docstring).

    #76: an item is netted exactly ONCE, at the DEEPEST level it appears in any demanded BOM (its
    low-level code) — so every parent's explosion has contributed the item's full dependent demand
    before it nets. Netting on first encounter instead used to DROP the dependent demand of a
    component that was already netted at a shallower level (independent reorder demand, or a
    diamond BOM sharing a component across levels), under-planning it.

    The BOM structure is fetched once by :func:`_bom_graph` (batched per frontier, each BOM read
    once); the per-item demand/supply reads reuse the bounded cross-module queries (no N+1)."""
    lines: list[_PlanLine] = []
    # Accumulated GROSS demand per item: independent up front, dependent added as parents explode.
    gross_demand: dict[uuid.UUID, Decimal] = await _gather_independent_demand(session, tenant_id)
    if not gross_demand:
        return lines
    levels, boms_by_item, components_by_bom = await _bom_graph(
        session, tenant_id, list(gross_demand)
    )
    for level in range(max(levels.values()) + 1):
        for item_id in [i for i, item_level in levels.items() if item_level == level]:
            gross = gross_demand.get(item_id, Decimal(0))
            if gross <= 0:
                continue  # reachable in the BOM graph but nothing demands it this run
            supply = await _net_supply(session, tenant_id, item_id)
            net = gross - supply
            if net <= 0:
                continue  # supply covers it — no planned order, no dependent demand
            net = _quantize_qty(net)
            bom = boms_by_item.get(item_id)
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
                    gross_demand[component_id] = (
                        gross_demand.get(component_id, Decimal(0)) + dependent
                    )
    return lines


async def _bom_graph(
    session: AsyncSession, tenant_id: uuid.UUID, roots: list[uuid.UUID]
) -> tuple[dict[uuid.UUID, int], dict[uuid.UUID, Bom], dict[uuid.UUID, list[BomComponent]]]:
    """The demanded BOM graph + each item's LOW-LEVEL CODE (#76).

    Structural BFS from the independently-demanded ``roots`` fetches every reachable item's active
    default BOM and components ONCE (two batched queries per frontier, a seen-set stops cycles).
    An in-memory relaxation then assigns each item the DEEPEST level it appears at, capped at
    ``MRP_MAX_EXPLOSION_LEVELS`` (the masters-rejected-but-defensive cycle guard). Returns
    ``(levels, boms_by_item, components_by_bom)`` so the netting pass reuses the cached BOMs."""
    boms_by_item: dict[uuid.UUID, Bom] = {}
    components_by_bom: dict[uuid.UUID, list[BomComponent]] = {}
    seen: set[uuid.UUID] = set(roots)
    frontier = list(dict.fromkeys(roots))
    while frontier:
        boms = await _active_boms_for(session, tenant_id, frontier)
        boms_by_item.update(boms)
        components_by_bom.update(
            await _components_for(session, tenant_id, [bom.id for bom in boms.values()])
        )
        next_frontier: list[uuid.UUID] = []
        for bom in boms.values():
            for component in components_by_bom.get(bom.id, []):
                if component.component_item_id not in seen:
                    seen.add(component.component_item_id)
                    next_frontier.append(component.component_item_id)
        frontier = next_frontier

    levels: dict[uuid.UUID, int] = dict.fromkeys(roots, 0)
    work: list[uuid.UUID] = list(levels)
    while work:
        item_id = work.pop()
        child_level = levels[item_id] + 1
        if child_level >= MRP_MAX_EXPLOSION_LEVELS:
            continue  # cycle guard: stop deepening rather than loop forever
        bom = boms_by_item.get(item_id)
        if bom is None:
            continue
        for component in components_by_bom.get(bom.id, []):
            component_id = component.component_item_id
            if levels.get(component_id, -1) < child_level:
                levels[component_id] = child_level
                work.append(component_id)
    return levels, boms_by_item, components_by_bom


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
