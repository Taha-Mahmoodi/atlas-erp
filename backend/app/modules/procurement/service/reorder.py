"""Reorder-point auto-requisitions (PLAN 6.4, D-042): scan inventory for items at/below their
reorder point and raise a DRAFT purchase requisition proposing replenishment.

Inventory OWNS reorder_point/reorder_quantity on the item (5.1) and exposes
``items_below_reorder_point`` (a set-based query, no N+1); the DRAFT requisition is a PROCUREMENT
document (6.2). So this scan reads the inventory query downward (STRUCTURE §5 — never imports
inventory models/service), then creates ONE requisition with a line per below-reorder item
(quantity = reorder_quantity, in the item's base UoM) via the existing 6.2 requisition create — so
the proposal flows through the normal requisition approval chain.

IDEMPOTENT dedup: a second scan the same day must not duplicate an open draft requisition line for
an item already proposed. ``open_requisition_item_ids`` collects the item ids already on any
DRAFT/SUBMITTED/APPROVED (un-converted) requisition line; the scan SKIPS those items. So re-running
the scan only adds genuinely new shortfalls. Returns the created requisition, or None when nothing
needs reordering (the endpoint maps None to a 200 "nothing to reorder").

PERFORMANCE §3: the scan is INLINE (a tenant's item count is modest in v1 and the work is two
set-based queries + one requisition insert). A per-tenant volume that outgrows the sync budget would
move it behind the existing job runner ('procurement.reorder_scan') — documented, not built for v1.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory import queries as inventory_queries
from app.modules.procurement.constants import RequisitionStatus
from app.modules.procurement.models import PurchaseRequisition, PurchaseRequisitionLine
from app.modules.procurement.schemas import RequisitionCreate, RequisitionLineCreate
from app.modules.procurement.service.requisitions import create_requisition

# A requisition line is still OPEN (its item should not be re-proposed) while the requisition is in
# any of these states — it has not been CONVERTED to a PO/RFQ, REJECTED or CANCELLED yet.
_OPEN_REQUISITION_STATUSES = (
    RequisitionStatus.DRAFT.value,
    RequisitionStatus.SUBMITTED.value,
    RequisitionStatus.APPROVED.value,
)


async def open_requisition_item_ids(
    session: AsyncSession, tenant_id: uuid.UUID
) -> set[uuid.UUID]:
    """The item ids already on an open (un-converted) requisition line (PLAN 6.4). The dedup guard:
    the reorder scan skips these so a re-run does not duplicate a still-open proposal. ONE set-based
    query joining lines to their open requisitions (no per-item N+1, PERFORMANCE §2)."""
    stmt = (
        select(PurchaseRequisitionLine.item_id)
        .join(
            PurchaseRequisition,
            (PurchaseRequisitionLine.tenant_id == PurchaseRequisition.tenant_id)
            & (PurchaseRequisitionLine.requisition_id == PurchaseRequisition.id),
        )
        .where(
            PurchaseRequisition.tenant_id == tenant_id,
            PurchaseRequisition.status.in_(_OPEN_REQUISITION_STATUSES),
        )
    )
    return {row[0] for row in (await session.execute(stmt)).all()}


async def run_reorder_scan(
    session: AsyncSession, tenant_id: uuid.UUID, *, requested_by: uuid.UUID | None = None
) -> PurchaseRequisition | None:
    """Scan for below-reorder items and raise a DRAFT requisition proposing replenishment (PLAN 6.4,
    D-042). Reads ``items_below_reorder_point`` (inventory, downward), skips items already on an
    open requisition line (the idempotent dedup), resolves each item's base UoM + a default
    currency, and
    creates ONE requisition with a line per remaining item (quantity = reorder_quantity) via the
    existing 6.2 create — so it flows through the normal approval chain. Returns the requisition, or
    None when nothing needs reordering (no shortfalls, or all already proposed)."""
    below = await inventory_queries.items_below_reorder_point(session, tenant_id)
    if not below:
        return None
    already_open = await open_requisition_item_ids(session, tenant_id)
    to_order = [(item_id, qty) for (item_id, _oh, _rp, qty) in below if item_id not in already_open]
    if not to_order:
        return None

    currency_code = await _default_currency(session, tenant_id)
    lines: list[RequisitionLineCreate] = []
    for item_id, reorder_quantity in to_order:
        base_uom_id = await inventory_queries.get_base_uom(session, tenant_id, item_id)
        if base_uom_id is None:
            continue
        lines.append(
            RequisitionLineCreate(
                item_id=item_id,
                description="Reorder-point replenishment",
                quantity=reorder_quantity,
                uom_id=base_uom_id,
                currency_code=currency_code,
            )
        )
    if not lines:
        return None
    return await create_requisition(
        session,
        tenant_id,
        RequisitionCreate(
            requested_by=requested_by, notes="Auto-generated reorder scan", lines=lines
        ),
    )


async def _default_currency(session: AsyncSession, tenant_id: uuid.UUID) -> str:
    """The currency code the reorder requisition lines carry (PLAN 6.4): the tenant's functional
    currency (the reporting currency, the natural default for an internal replenishment estimate
    with no vendor yet). Reads finance/queries downward; falls back to USD when unconfigured (the
    same single-currency default the costing path uses)."""
    from app.modules.finance import queries as finance_queries

    return await finance_queries.functional_currency_or_none(session, tenant_id) or "USD"
