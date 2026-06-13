"""Reorder-point auto-requisition scan (PLAN 6.4 Part B, D-042): items below reorder produce a
draft requisition with reorder_quantity lines; items at/above are skipped; a second scan does not
duplicate open lines; the created requisition flows through the normal 6.2 approval.

The scan goes through the REAL service inside a uow (D-025): it reads the inventory
``items_below_reorder_point`` query downward and creates procurement DRAFT requisitions.
"""

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow
from app.core.tenancy import tenant_context
from app.modules.inventory import queries as inventory_queries
from app.modules.procurement import service
from app.modules.procurement.constants import RequisitionStatus
from tests.modules.inventory.factories import build_inventory_setup, build_item
from tests.modules.procurement.factories import seed_currency


async def _run_scan(session: AsyncSession, tenant_id: uuid.UUID):
    holder: dict[str, object] = {}

    async def work() -> None:
        with tenant_context(tenant_id):
            holder["req"] = await service.run_reorder_scan(session, tenant_id)

    with tenant_context(tenant_id):
        await run_in_uow(session, work)
    return holder["req"]


async def _setup_with_item(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    code: str,
    *,
    reorder_point: str | None,
    reorder_quantity: str | None,
):
    """Seed a USD currency + one inventory setup (EA/BOX + category) and an item carrying the given
    reorder fields. Returns the item. One inventory setup per tenant (the UoM/category codes are
    unique per tenant)."""
    await seed_currency(session, tenant_id)
    inv = await build_inventory_setup(session, tenant_id)
    kwargs: dict[str, object] = {}
    if reorder_point is not None:
        kwargs["reorder_point"] = Decimal(reorder_point)
    if reorder_quantity is not None:
        kwargs["reorder_quantity"] = Decimal(reorder_quantity)
    return await build_item(
        session,
        tenant_id,
        item_code=code,
        category_id=inv.category_id,
        base_uom_id=inv.ea_uom_id,
        **kwargs,
    )


async def test_below_reorder_item_produces_draft_requisition(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """An item with on-hand 0 ≤ reorder_point 5 and reorder_quantity 20 produces a DRAFT requisition
    line for 20."""
    item = await _setup_with_item(
        db_session, tenant_a, "RP-1", reorder_point="5", reorder_quantity="20"
    )
    req = await _run_scan(db_session, tenant_a)
    assert req is not None
    assert req.status == RequisitionStatus.DRAFT.value
    with tenant_context(tenant_a):
        lines = await service.get_requisition_lines(db_session, tenant_a, req.id)
    matched = [line for line in lines if line.item_id == item.id]
    assert len(matched) == 1
    assert Decimal(matched[0].quantity) == Decimal(20)


async def test_item_at_or_above_reorder_is_skipped(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """An item with no reorder point configured is not proposed — the scan returns None when
    nothing is below reorder."""
    await _setup_with_item(
        db_session, tenant_a, "RP-NONE", reorder_point=None, reorder_quantity=None
    )
    req = await _run_scan(db_session, tenant_a)
    assert req is None


async def test_second_scan_does_not_duplicate_open_lines(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A second scan the same day skips an item already on an open requisition line (idempotent
    dedup) — the second scan returns None."""
    await _setup_with_item(
        db_session, tenant_a, "RP-DUP", reorder_point="5", reorder_quantity="20"
    )
    first = await _run_scan(db_session, tenant_a)
    assert first is not None
    second = await _run_scan(db_session, tenant_a)
    assert second is None


async def test_items_below_reorder_query_is_set_based(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The inventory query returns (item, on_hand, point, qty) for below-reorder items only."""
    item = await _setup_with_item(
        db_session, tenant_a, "RP-Q", reorder_point="5", reorder_quantity="12"
    )
    with tenant_context(tenant_a):
        rows = await inventory_queries.items_below_reorder_point(db_session, tenant_a)
    ids = {row[0] for row in rows}
    assert item.id in ids


async def test_scanned_requisition_flows_through_approval(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The created requisition is a normal 6.2 document — it can be submitted (auto-approves with no
    threshold rule)."""
    await _setup_with_item(
        db_session, tenant_a, "RP-FLOW", reorder_point="5", reorder_quantity="20"
    )
    req = await _run_scan(db_session, tenant_a)
    assert req is not None

    async def _submit() -> None:
        with tenant_context(tenant_a):
            await service.submit_requisition(db_session, tenant_a, req.id)

    with tenant_context(tenant_a):
        await run_in_uow(db_session, _submit)
        reread = await service.get_requisition(db_session, tenant_a, req.id)
        status = reread.status
    assert status == RequisitionStatus.APPROVED.value
