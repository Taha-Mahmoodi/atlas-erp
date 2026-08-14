"""Write-path statement budgets (Phase 19 ratchet).

PERFORMANCE §2's <=3 rule is a LIST-ENDPOINT rule (tests/conftest.py:149-171) and
tests/perf/test_budgets.py times only read paths, so nothing has ever bounded a WRITE. Q4 of
docs/research/hospitality-industry-plan.md measured one ingredient ISSUE move and the whole
Phase 19 design turns on that number, so it gets a ceiling here before the feature lands.

These are CEILINGS, not targets. A number moving down is good and the ceiling should follow it
down; a number moving up is a regression that must be explained in the PR that causes it.

Deliberately NOT marked ``perf``: the perf marker is for wall-clock budgets, which are excluded
from the blocking CI job (``-m "not pg and not perf"``) because timings are machine-dependent. A
statement count is deterministic, so this ratchet runs in the DEFAULT suite where it can actually
block a regression.
"""

import uuid
from collections.abc import Callable
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow
from app.core.tenancy import tenant_context
from app.main import register_event_handlers
from app.modules.inventory import service
from app.modules.inventory.constants import MoveType
from app.modules.inventory.schemas import StockMoveCreate
from tests.conftest import QueryCounter
from tests.modules.inventory.factories import build_stock, build_stock_setup

# Measured on this branch at 38 statements, confirming Q4's number exactly. Headroom for
# incidental growth, not for a design that multiplies the count.
STOCK_MOVE_ISSUE_CEILING = 45


async def test_single_ingredient_issue_move_stays_within_its_ceiling(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """One ISSUE move through the real write path: create_move (validation, docflow, gapless
    number, quant delta, costing) plus the D-011 dispatch of StockValued into the finance COGS
    handler, all inside one uow. That is the unit a fired restaurant ticket multiplies by every
    distinct component, which is why Phase 19 aggregates components and backgrounds depletion
    instead of issuing one move per ticket line inline.
    """
    # The app factory subscribes the inventory->finance COGS handler; the autouse
    # clear_event_subscriptions fixture wipes it, so a service-level test must re-register or it
    # measures a write that never posts its journal (tests/modules/inventory/conftest.py:32-41).
    register_event_handlers()
    setup = await build_stock_setup(db_session, tenant_a)
    await build_stock(db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal("100"))
    payload = StockMoveCreate(
        move_type=MoveType.ISSUE,
        item_id=setup.item_id,
        quantity=Decimal("1"),
        from_bin_id=setup.bin_a_id,
    )

    async def issue() -> None:
        with tenant_context(tenant_a):
            await service.create_move(db_session, tenant_a, payload)

    with query_counter() as counted, tenant_context(tenant_a):
        await run_in_uow(db_session, issue)

    assert counted.count <= STOCK_MOVE_ISSUE_CEILING, (
        f"one ingredient issue now costs {counted.count} statements "
        f"(ceiling {STOCK_MOVE_ISSUE_CEILING}); a rise here multiplies by every component on "
        "every ticket:\n" + "\n".join(counted.statements)
    )
    print(f"\n[perf] single ingredient ISSUE move: {counted.count} statements")
