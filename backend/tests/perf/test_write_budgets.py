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
from app.modules.hospitality.service import tickets
from app.modules.inventory import service
from app.modules.inventory.constants import MoveType
from app.modules.inventory.schemas import StockMoveCreate
from tests.conftest import QueryCounter
from tests.modules.hospitality.factories import build_kitchen, build_open_ticket
from tests.modules.inventory.factories import build_stock, build_stock_setup

# Measured on this branch at 38 statements, confirming Q4's number exactly. Headroom for
# incidental growth, not for a design that multiplies the count.
STOCK_MOVE_ISSUE_CEILING = 45

# The OTHER half of the same argument: what the guest's request costs once depletion is off it.
# MEASURED at 10 statements for an 8-dish ticket exploding to 12 distinct ingredients — against
# 12 x 38 = 456 if those ingredients were issued inline. Headroom for incidental growth only: any
# ceiling near the per-ingredient cost means depletion has moved back onto the sale.
FIRED_TICKET_CEILING = 14


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


async def test_firing_a_ticket_stays_within_its_ceiling(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """Firing a ticket is the request a guest and a server actually wait on, and Phase 19's whole
    claim is that it stays CHEAP AND FLAT while the expensive part (38 statements per ingredient)
    moves into a background job.

    An 8-dish ticket exploding to 12 distinct ingredients costs 10 statements: the availability
    read, the ticket UPDATE + its audit row, the docflow status, the recipe explosion's three
    reads and the job INSERT. The ceiling sits an order of magnitude under the 456 those same 12
    ingredients would cost issued inline, so it also enforces the flatness claim — a count that
    grows with the ingredient count cannot stay under it. A regression here means depletion has
    crept back onto the sale (Q4), the exact failure this phase exists to prevent, and no
    behavioural test would notice.
    """
    register_event_handlers()
    pool = [f"ING-{index:02d}" for index in range(12)]
    recipes = {
        f"DISH-{dish:02d}": {pool[(dish + offset) % len(pool)]: Decimal(1) for offset in range(7)}
        for dish in range(8)
    }
    kitchen = await build_kitchen(db_session, tenant_a, recipes, stock=Decimal(500))
    ticket_id = await build_open_ticket(
        db_session, tenant_a, [(kitchen.dishes[code], "1") for code in recipes]
    )

    async def fire() -> None:
        await tickets.fire_ticket(db_session, tenant_a, ticket_id)

    with query_counter() as counted, tenant_context(tenant_a):
        await run_in_uow(db_session, fire)

    assert counted.count <= FIRED_TICKET_CEILING, (
        f"firing an 8-dish ticket now costs {counted.count} statements "
        f"(ceiling {FIRED_TICKET_CEILING}); if depletion has moved back onto the sale this is "
        "where it shows:\n" + "\n".join(counted.statements)
    )
    print(f"\n[perf] firing an 8-dish / 12-ingredient ticket: {counted.count} statements")
