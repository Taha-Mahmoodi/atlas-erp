"""Production-order service tests (PLAN 8.2, D-048): create+explode, release, issue-to-WIP,
finish-to-stock, the WIP-nets-to-zero proof, and the variance flush.

The KEY accounting invariant proven here (the 6.4 GR/IR-clears-to-zero / 7.4 precedent): once an
order is fully issued + finished, the WIP clearing account nets to ZERO, the finished item's
inventory value equals the issued component cost, and any over/under-absorption holds in the
production-variance account — all read off the trial balance (finance/queries.account_balances).
The lifecycle/rollback/RBAC/isolation tests live in test_production_orders_lifecycle.py; shared
helpers in _production_shared.py.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailedError
from app.modules.manufacturing import service
from app.modules.manufacturing.constants import ProductionOrderStatus
from app.modules.manufacturing.schemas import (
    FinishOrderRequest,
    IssueComponentsRequest,
    ProductionOrderCreate,
)
from tests.modules.manufacturing._production_shared import (
    balance,
    components,
    create_order,
    get_order,
    item_value,
    on_hand,
    run,
)
from tests.modules.manufacturing.production_factories import (
    build_production_order,
    build_production_order_setup,
)

pytestmark = pytest.mark.asyncio


# --- create + explode ---------------------------------------------------------


async def test_create_explodes_components_with_scrap(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """required_quantity = quantity_per × order_qty × (1 + scrap_percent/100). With qty_per=2,
    order_qty=5, scrap=10% → 2 × 5 × 1.10 = 11."""
    setup = await build_production_order_setup(
        db_session, tenant_a, quantity_per=Decimal(2), scrap_percent=Decimal(10)
    )
    order = await create_order(db_session, setup, quantity=Decimal(5))
    assert order.status == ProductionOrderStatus.DRAFT.value
    assert order.order_number.startswith("MO")
    rows = await components(db_session, tenant_a, order.id)
    assert len(rows) == 1
    assert Decimal(rows[0].required_quantity) == Decimal(11)
    assert Decimal(rows[0].issued_quantity) == 0


async def test_create_without_active_bom_is_422(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """An item with no active default BOM and no supplied bom_id → manufacturing.no_active_bom."""
    setup = await build_production_order_setup(db_session, tenant_a)
    with pytest.raises(ValidationFailedError) as exc:
        await build_production_order(
            db_session,
            tenant_a,
            ProductionOrderCreate(
                item_id=setup.component_item_id,
                quantity=Decimal(1),
                warehouse_id=setup.warehouse_id,
            ),
        )
    assert exc.value.code == "manufacturing.no_active_bom"


# --- release ------------------------------------------------------------------


async def test_release_moves_to_released(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup = await build_production_order_setup(db_session, tenant_a)
    order = await create_order(db_session, setup)
    await run(db_session, tenant_a, lambda: service.release_order(db_session, tenant_a, order.id))
    refreshed = await get_order(db_session, tenant_a, order.id)
    assert refreshed.status == ProductionOrderStatus.RELEASED.value
    assert refreshed.released_at is not None


# --- issue components → Dr WIP / Cr Inventory ---------------------------------


async def test_issue_components_posts_wip_journal_and_drops_on_hand(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Issuing all required components creates ISSUE moves: component on-hand drops, the WIP account
    is DEBITED and inventory CREDITED at the component cost (qty_per=2 × order 5 × $3 = $30)."""
    setup = await build_production_order_setup(db_session, tenant_a, component_unit_cost=Decimal(3))
    order = await create_order(db_session, setup, quantity=Decimal(5))
    on_hand_before = await on_hand(db_session, tenant_a, setup.component_item_id, setup.bin_id)
    inventory_before = await balance(db_session, tenant_a, setup.inventory_account_id)
    await run(db_session, tenant_a, lambda: service.release_order(db_session, tenant_a, order.id))
    await run(
        db_session,
        tenant_a,
        lambda: service.issue_components(
            db_session, tenant_a, order.id, IssueComponentsRequest()
        ),
    )
    refreshed = await get_order(db_session, tenant_a, order.id)
    assert refreshed.status == ProductionOrderStatus.IN_PROGRESS.value
    on_hand_after = await on_hand(db_session, tenant_a, setup.component_item_id, setup.bin_id)
    assert on_hand_before - on_hand_after == Decimal(10)  # 2 × 5
    assert Decimal(refreshed.accumulated_wip_cost) == Decimal(30)  # 10 × $3
    # The issue DEBITED WIP $30 and CREDITED inventory $30 (Dr WIP / Cr Inventory).
    assert await balance(db_session, tenant_a, setup.wip_account_id) == Decimal(30)
    inventory_after = await balance(db_session, tenant_a, setup.inventory_account_id)
    assert inventory_before - inventory_after == Decimal(30)


# --- finish → Dr Inventory / Cr WIP + WIP nets to zero ------------------------


async def test_full_flow_wip_nets_to_zero(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """End-to-end: issue all components, finish the whole order → the WIP account balance is EXACTLY
    zero, and the finished item's inventory value equals the issued component cost (the 6.4/7.4
    nets-to-zero precedent applied to manufacturing)."""
    setup = await build_production_order_setup(db_session, tenant_a, component_unit_cost=Decimal(3))
    order = await create_order(db_session, setup, quantity=Decimal(5))
    inventory_before = await balance(db_session, tenant_a, setup.inventory_account_id)
    await run(db_session, tenant_a, lambda: service.release_order(db_session, tenant_a, order.id))
    await run(
        db_session,
        tenant_a,
        lambda: service.issue_components(
            db_session, tenant_a, order.id, IssueComponentsRequest()
        ),
    )
    await run(
        db_session,
        tenant_a,
        lambda: service.finish_order(
            db_session,
            tenant_a,
            order.id,
            FinishOrderRequest(
                finished_quantity=Decimal(5), finished_bin_id=setup.finished_bin_id
            ),
        ),
    )
    refreshed = await get_order(db_session, tenant_a, order.id)
    assert refreshed.status == ProductionOrderStatus.FINISHED.value
    assert Decimal(refreshed.finished_quantity) == Decimal(5)
    assert Decimal(refreshed.accumulated_wip_cost) == 0
    # THE INVARIANT: WIP nets to ZERO once fully issued + finished.
    assert await balance(db_session, tenant_a, setup.wip_account_id) == Decimal(0)
    # The inventory account NET over issue+finish is zero (Cr $30 on issue, Dr $30 on the finished
    # receipt) — the value moved out of components and into the finished good at the same $30.
    assert await balance(db_session, tenant_a, setup.inventory_account_id) == inventory_before
    # The finished item's inventory VALUE = the issued component cost ($30).
    assert await item_value(db_session, tenant_a, setup.parent_item_id) == Decimal(30)
    finished_on_hand = await on_hand(
        db_session, tenant_a, setup.parent_item_id, setup.finished_bin_id
    )
    assert finished_on_hand == Decimal(5)


async def test_variance_holds_residual_and_wip_still_zero(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A non-divisible accumulated WIP ($10 over 3 ordered units → $3.33/unit) leaves a rounding
    residual the variance account absorbs; WIP still nets to ZERO."""
    setup = await build_production_order_setup(
        db_session,
        tenant_a,
        component_unit_cost=Decimal(1),
        quantity_per=Decimal("3.333333"),
    )
    # qty_per=3.333333 × order 3 → ~10 units × $1 = $10 WIP; $10/3 = $3.33/unit → 3 × $3.33 = $9.99
    # received, $0.01 residual to variance.
    order = await create_order(db_session, setup, quantity=Decimal(3))
    await run(db_session, tenant_a, lambda: service.release_order(db_session, tenant_a, order.id))
    await run(
        db_session,
        tenant_a,
        lambda: service.issue_components(
            db_session, tenant_a, order.id, IssueComponentsRequest()
        ),
    )
    await run(
        db_session,
        tenant_a,
        lambda: service.finish_order(
            db_session,
            tenant_a,
            order.id,
            FinishOrderRequest(
                finished_quantity=Decimal(3), finished_bin_id=setup.finished_bin_id
            ),
        ),
    )
    # THE INVARIANT holds even with a residual: WIP nets to ZERO (issue debit = finished-receipt
    # credit + variance flush).
    assert await balance(db_session, tenant_a, setup.wip_account_id) == Decimal(0)
    # The residual ($10.00 issued − $9.99 absorbed) — a one-cent under-absorption — sits in the
    # variance account as a DEBIT (cost exceeded absorbed).
    assert await balance(db_session, tenant_a, setup.variance_account_id) == Decimal("0.01")
    # The finished item entered stock at the absorbed value ($9.99 = 3 × $3.33).
    assert await item_value(db_session, tenant_a, setup.parent_item_id) == Decimal("9.99")
