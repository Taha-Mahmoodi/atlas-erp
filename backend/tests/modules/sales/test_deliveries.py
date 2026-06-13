"""Delivery service behaviour (PLAN 7.3, D-045): create draft, post (the full delivery → stock-issue
→ COGS-journal → order-update chain), over-delivery rejection, order-not-confirmed rejection,
partial
vs full delivery + backorders, insufficient-stock rollback, closed-period rollback, lot delivery,
idempotency, cancel, and the ATP committed-quantity shrink after delivery.

Deliveries go through the REAL service inside a uow (D-025); the sales conftest's autouse fixture
registers the sales→inventory + inventory→finance handlers, so a posted delivery issues stock and
posts the COGS journal exactly as in production. These tests assert the posted state directly.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.finance import queries as finance_queries
from app.modules.finance import service as finance_service
from app.modules.finance.constants.enums import DocumentType
from app.modules.finance.models import JournalEntry, JournalLine
from app.modules.inventory import queries as inventory_queries
from app.modules.sales import queries as sales_queries
from app.modules.sales import service
from app.modules.sales.constants import (
    DELIVERY_MOVED_BY_STOCK_MOVE_LINK,
    ORDER_DELIVERED_BY_DELIVERY_LINK,
    DeliveryStatus,
    SalesOrderStatus,
)
from app.modules.sales.schemas import DeliveryLineCreate
from tests.modules.sales.factories import (
    OrderSetup,
    build_confirmed_order,
    build_delivery,
    build_order_setup,
    build_sales_order,
    post_delivery,
    seed_on_hand,
    seed_on_hand_lot,
)


async def _order_line_id(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> uuid.UUID:
    with tenant_context(tenant_id):
        lines = await service.get_sales_order_lines(session, tenant_id, order_id)
    return lines[0].id


def _line(
    order_line_id: uuid.UUID, bin_id: uuid.UUID, qty: str, **kw: object
) -> DeliveryLineCreate:
    return DeliveryLineCreate(
        sales_order_line_id=order_line_id,
        bin_id=bin_id,
        quantity=Decimal(qty),
        **kw,  # type: ignore[arg-type]
    )


async def _on_hand(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> Decimal:
    with tenant_context(tenant_id):
        return await inventory_queries.total_on_hand(session, tenant_id, item_id)


async def _cogs_journal_lines(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[JournalLine]:
    with tenant_context(tenant_id):
        entries = (
            await session.execute(
                select(JournalEntry).where(
                    JournalEntry.tenant_id == tenant_id,
                    JournalEntry.document_type == DocumentType.COGS.value,
                )
            )
        ).scalars().all()
        lines: list[JournalLine] = []
        for entry in entries:
            lines.extend(
                (
                    await session.execute(
                        select(JournalLine).where(JournalLine.journal_entry_id == entry.id)
                    )
                )
                .scalars()
                .all()
            )
        return lines


def _debit(lines: list[JournalLine], account_id: uuid.UUID) -> Decimal:
    return sum(
        (Decimal(ln.transaction_debit_amount) for ln in lines if ln.account_id == account_id),
        Decimal(0),
    )


def _credit(lines: list[JournalLine], account_id: uuid.UUID) -> Decimal:
    return sum(
        (Decimal(ln.transaction_credit_amount) for ln in lines if ln.account_id == account_id),
        Decimal(0),
    )


@pytest.fixture
async def order_setup(db_session: AsyncSession, tenant_a: uuid.UUID) -> OrderSetup:
    return await build_order_setup(db_session, tenant_a)


# --- Create draft -------------------------------------------------------------


async def test_create_delivery_is_draft_with_dn_number(
    db_session: AsyncSession, order_setup: OrderSetup
) -> None:
    """A created delivery is DRAFT, carries a DN number, snapshots the customer, moves no stock."""
    await seed_on_hand(db_session, order_setup, "10")
    order = await build_confirmed_order(db_session, order_setup, quantity="5")
    line_id = await _order_line_id(db_session, order_setup.tenant_id, order.id)
    delivery = await build_delivery(
        db_session,
        order_setup,
        order_id=order.id,
        lines=[_line(line_id, order_setup.bin_id, "3")],
    )
    assert delivery.status == DeliveryStatus.DRAFT.value
    assert delivery.delivery_number.startswith("DN-")
    assert delivery.customer_id == order_setup.customer_id
    on_hand = await _on_hand(db_session, order_setup.tenant_id, order_setup.item_id)
    assert on_hand == Decimal(10)  # nothing issued yet


async def test_create_rejects_over_delivery(
    db_session: AsyncSession, order_setup: OrderSetup
) -> None:
    """Delivering more than the order line's open-to-deliver quantity → 422 sales.over_delivery."""
    await seed_on_hand(db_session, order_setup, "10")
    order = await build_confirmed_order(db_session, order_setup, quantity="5")
    line_id = await _order_line_id(db_session, order_setup.tenant_id, order.id)
    with pytest.raises(ValidationFailedError) as exc:
        await build_delivery(
            db_session,
            order_setup,
            order_id=order.id,
            lines=[_line(line_id, order_setup.bin_id, "6")],  # ordered 5
        )
    assert exc.value.code == "sales.over_delivery"


async def test_create_rejects_unconfirmed_order(
    db_session: AsyncSession, order_setup: OrderSetup
) -> None:
    """A DRAFT (unconfirmed) order cannot ship a delivery → 422 sales.order_not_confirmed."""
    await seed_on_hand(db_session, order_setup, "10")
    order = await build_sales_order(
        db_session,
        order_setup.tenant_id,
        customer_id=order_setup.customer_id,
        item_id=order_setup.item_id,
        uom_id=order_setup.uom_id,
        quantity="5",
    )
    line_id = await _order_line_id(db_session, order_setup.tenant_id, order.id)
    with pytest.raises(ValidationFailedError) as exc:
        await build_delivery(
            db_session,
            order_setup,
            order_id=order.id,
            lines=[_line(line_id, order_setup.bin_id, "3")],
        )
    assert exc.value.code == "sales.order_not_confirmed"


async def test_create_rejects_insufficient_stock_at_bin(
    db_session: AsyncSession, order_setup: OrderSetup
) -> None:
    """Delivering more than the source bin holds is pre-rejected → 422 sales.insufficient_stock."""
    await seed_on_hand(db_session, order_setup, "2")  # only 2 on hand at the bin
    order = await build_confirmed_order(db_session, order_setup, quantity="5")
    line_id = await _order_line_id(db_session, order_setup.tenant_id, order.id)
    with pytest.raises(ValidationFailedError) as exc:
        await build_delivery(
            db_session,
            order_setup,
            order_id=order.id,
            lines=[_line(line_id, order_setup.bin_id, "4")],  # bin holds 2
        )
    assert exc.value.code == "sales.insufficient_stock"


# --- Post: the full chain -----------------------------------------------------


async def test_post_issues_stock_and_posts_cogs_journal(
    db_session: AsyncSession, order_setup: OrderSetup
) -> None:
    """Posting a delivery creates a stock ISSUE move (on-hand DOWN) and a balanced Dr COGS / Cr
    Inventory journal at the issue cost (D-045), via the event bus — COGS the default issue
    offset."""
    setup = order_setup
    # Seed 10 @ unit_cost 2 so the moving-average issue cost is 2/unit; deliver 3 ⇒ COGS 6.
    await seed_on_hand_for_cost(db_session, setup, "10", unit_cost="2")
    order = await build_confirmed_order(db_session, setup, quantity="5")
    line_id = await _order_line_id(db_session, setup.tenant_id, order.id)
    delivery = await build_delivery(
        db_session, setup, order_id=order.id, lines=[_line(line_id, setup.bin_id, "3")]
    )
    posted = await post_delivery(db_session, setup.tenant_id, delivery.id)
    assert posted.status == DeliveryStatus.POSTED.value
    assert posted.posted_at is not None

    on_hand = await _on_hand(db_session, setup.tenant_id, setup.item_id)
    assert on_hand == Decimal(7)  # 10 − 3 issued

    lines = await _cogs_journal_lines(db_session, setup.tenant_id)
    assert _debit(lines, setup.cogs_account_id) == Decimal(6)  # 3 @ 2
    assert _credit(lines, setup.inventory_account_id) == Decimal(6)


async def test_post_advances_order_partial_then_delivered(
    db_session: AsyncSession, order_setup: OrderSetup
) -> None:
    """A partial delivery raises delivered_quantity + sets PARTIALLY_DELIVERED; a second delivery
    completes the line and sets the order DELIVERED (backorder closed)."""
    setup = order_setup
    await seed_on_hand(db_session, setup, "10")
    order = await build_confirmed_order(db_session, setup, quantity="5")
    line_id = await _order_line_id(db_session, setup.tenant_id, order.id)

    d1 = await build_delivery(
        db_session, setup, order_id=order.id, lines=[_line(line_id, setup.bin_id, "2")]
    )
    await post_delivery(db_session, setup.tenant_id, d1.id)
    with tenant_context(setup.tenant_id):
        reloaded = await service.get_sales_order(db_session, setup.tenant_id, order.id)
        assert reloaded.status == SalesOrderStatus.PARTIALLY_DELIVERED.value
        open_qty = await sales_queries.so_line_open_to_deliver(db_session, setup.tenant_id, line_id)
    assert open_qty == Decimal(3)

    d2 = await build_delivery(
        db_session, setup, order_id=order.id, lines=[_line(line_id, setup.bin_id, "3")]
    )
    await post_delivery(db_session, setup.tenant_id, d2.id)
    with tenant_context(setup.tenant_id):
        reloaded = await service.get_sales_order(db_session, setup.tenant_id, order.id)
    assert reloaded.status == SalesOrderStatus.DELIVERED.value


async def test_post_links_docflow_order_delivery_move(
    db_session: AsyncSession, order_setup: OrderSetup
) -> None:
    """The docflow chain runs order → delivery (delivered_by) → move (moved_by) after a post."""
    setup = order_setup
    await seed_on_hand(db_session, setup, "10")
    order = await build_confirmed_order(db_session, setup, quantity="5")
    line_id = await _order_line_id(db_session, setup.tenant_id, order.id)
    delivery = await build_delivery(
        db_session, setup, order_id=order.id, lines=[_line(line_id, setup.bin_id, "3")]
    )
    await post_delivery(db_session, setup.tenant_id, delivery.id)

    with tenant_context(setup.tenant_id):
        reloaded = await service.get_delivery(db_session, setup.tenant_id, delivery.id)
        chain = await docflow.get_document_chain(
            db_session, setup.tenant_id, reloaded.document_id
        )
    link_types = {edge.link_type for edge in chain.edges}
    assert ORDER_DELIVERED_BY_DELIVERY_LINK in link_types
    assert DELIVERY_MOVED_BY_STOCK_MOVE_LINK in link_types


async def test_post_insufficient_stock_is_rejected(
    db_session: AsyncSession, order_setup: OrderSetup
) -> None:
    """If the bin's stock is drained AFTER the draft, the post fails at the stock issue — the
    inventory move's no-negative-stock guard surfaces InsufficientStockError, so the delivery
    cannot ship goods it doesn't have. The all-or-nothing ROLLBACK of a failed post is proven by
    ``test_post_closed_period_rolls_back`` (same ``run_in_uow`` path, readable state because a
    DB-trigger failure doesn't poison the aiosqlite connection the way a handler-raised Python
    exception does — see #53); here we pin the rejection itself."""
    setup = order_setup
    await seed_on_hand(db_session, setup, "5")
    order = await build_confirmed_order(db_session, setup, quantity="5")
    line_id = await _order_line_id(db_session, setup.tenant_id, order.id)
    delivery = await build_delivery(
        db_session, setup, order_id=order.id, lines=[_line(line_id, setup.bin_id, "5")]
    )
    delivery_id = delivery.id
    # Drain the bin via an ISSUE so the delivery's post finds nothing to issue.
    from app.modules.inventory.constants import MoveType
    from app.modules.inventory.schemas import StockMoveCreate
    from tests.modules.inventory.factories import build_move

    await build_move(
        db_session,
        setup.tenant_id,
        StockMoveCreate(
            move_type=MoveType.ISSUE,
            item_id=setup.item_id,
            quantity=Decimal(5),
            from_bin_id=setup.bin_id,
        ),
    )

    with pytest.raises(ValidationFailedError) as exc:
        await post_delivery(db_session, setup.tenant_id, delivery_id)
    assert exc.value.code == "inventory.insufficient_stock"


async def test_post_closed_period_rolls_back(
    db_session: AsyncSession, order_setup: OrderSetup
) -> None:
    """A delivery dated into a CLOSED period trips the move's COGS-journal period trigger and rolls
    the WHOLE post back — no stock issued, delivery still DRAFT (D-045 all-or-nothing)."""
    setup = order_setup
    await seed_on_hand(db_session, setup, "10")
    order = await build_confirmed_order(db_session, setup, quantity="5")
    line_id = await _order_line_id(db_session, setup.tenant_id, order.id)
    delivery = await build_delivery(
        db_session,
        setup,
        order_id=order.id,
        lines=[_line(line_id, setup.bin_id, "3")],
        delivery_date=date(2026, 3, 15),
    )
    delivery_id = delivery.id
    with tenant_context(setup.tenant_id):
        period = await finance_queries.find_period_for_date(
            db_session, setup.tenant_id, date(2026, 3, 15)
        )
        await finance_service.close_period(db_session, setup.tenant_id, period.id)
        await db_session.commit()

    with pytest.raises(Exception):  # noqa: B017 - period trigger / service error
        await post_delivery(db_session, setup.tenant_id, delivery_id)

    on_hand = await _on_hand(db_session, setup.tenant_id, setup.item_id)
    assert on_hand == Decimal(10)  # nothing issued
    with tenant_context(setup.tenant_id):
        reloaded = await service.get_delivery(db_session, setup.tenant_id, delivery_id)
    assert reloaded.status == DeliveryStatus.DRAFT.value


async def test_post_is_idempotent_reject(
    db_session: AsyncSession, order_setup: OrderSetup
) -> None:
    """Re-posting a POSTED delivery is rejected (a posted delivery is terminal)."""
    setup = order_setup
    await seed_on_hand(db_session, setup, "10")
    order = await build_confirmed_order(db_session, setup, quantity="5")
    line_id = await _order_line_id(db_session, setup.tenant_id, order.id)
    delivery = await build_delivery(
        db_session, setup, order_id=order.id, lines=[_line(line_id, setup.bin_id, "3")]
    )
    await post_delivery(db_session, setup.tenant_id, delivery.id)
    with pytest.raises(ConflictError) as exc:
        await post_delivery(db_session, setup.tenant_id, delivery.id)
    assert exc.value.code == "sales.delivery_already_posted"


async def test_post_lot_delivery_issues_the_lot(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A delivery of a lot-tracked item issues the named lot (D-045): on-hand for that lot drops."""
    setup = await build_order_setup(db_session, tenant_a, tracking_mode="LOT")
    await seed_on_hand_lot(db_session, setup, "10", lot_code="LOT-A")
    order = await build_confirmed_order(db_session, setup, quantity="5")
    line_id = await _order_line_id(db_session, setup.tenant_id, order.id)
    delivery = await build_delivery(
        db_session,
        setup,
        order_id=order.id,
        lines=[_line(line_id, setup.bin_id, "3", lot_code="LOT-A")],
    )
    await post_delivery(db_session, setup.tenant_id, delivery.id)
    on_hand = await _on_hand(db_session, setup.tenant_id, setup.item_id)
    assert on_hand == Decimal(7)


# --- Cancel -------------------------------------------------------------------


async def test_cancel_draft_only(
    db_session: AsyncSession, order_setup: OrderSetup
) -> None:
    """A DRAFT delivery cancels; a POSTED delivery is terminal (cannot be cancelled)."""
    setup = order_setup
    await seed_on_hand(db_session, setup, "10")
    order = await build_confirmed_order(db_session, setup, quantity="5")
    line_id = await _order_line_id(db_session, setup.tenant_id, order.id)
    d1 = await build_delivery(
        db_session, setup, order_id=order.id, lines=[_line(line_id, setup.bin_id, "2")]
    )

    async def _cancel(did: uuid.UUID) -> None:
        from app.core.events import run_in_uow

        async def work() -> None:
            with tenant_context(setup.tenant_id):
                await service.cancel_delivery(db_session, setup.tenant_id, did)

        with tenant_context(setup.tenant_id):
            await run_in_uow(db_session, work)

    await _cancel(d1.id)
    with tenant_context(setup.tenant_id):
        reloaded = await service.get_delivery(db_session, setup.tenant_id, d1.id)
    assert reloaded.status == DeliveryStatus.CANCELLED.value

    d2 = await build_delivery(
        db_session, setup, order_id=order.id, lines=[_line(line_id, setup.bin_id, "2")]
    )
    await post_delivery(db_session, setup.tenant_id, d2.id)
    with pytest.raises(ConflictError) as exc:
        await _cancel(d2.id)
    assert exc.value.code == "sales.delivery_not_cancellable"


# --- ATP cross-check (PLAN 7.2 → 7.3) -----------------------------------------


async def test_committed_quantity_shrinks_after_delivery(
    db_session: AsyncSession, order_setup: OrderSetup
) -> None:
    """A delivered quantity is no longer 'committed undelivered' — the 7.2 committed-quantity ATP
    component shrinks by exactly the delivered amount after a post (D-044/D-045 cross-check)."""
    setup = order_setup
    await seed_on_hand(db_session, setup, "10")
    order = await build_confirmed_order(db_session, setup, quantity="5")
    line_id = await _order_line_id(db_session, setup.tenant_id, order.id)
    with tenant_context(setup.tenant_id):
        before = await sales_queries.committed_quantity(db_session, setup.tenant_id, setup.item_id)
    assert before == Decimal(5)

    delivery = await build_delivery(
        db_session, setup, order_id=order.id, lines=[_line(line_id, setup.bin_id, "2")]
    )
    await post_delivery(db_session, setup.tenant_id, delivery.id)
    with tenant_context(setup.tenant_id):
        after = await sales_queries.committed_quantity(db_session, setup.tenant_id, setup.item_id)
    assert after == Decimal(3)  # 5 committed − 2 delivered


# --- Helper: seed on-hand at a specific cost ----------------------------------


async def seed_on_hand_for_cost(
    session: AsyncSession, setup: OrderSetup, quantity: str, *, unit_cost: str
) -> None:
    """Seed on-hand stock at a specific entry cost so the issue COGS is deterministic (D-025)."""
    from tests.modules.inventory.factories import build_stock

    await build_stock(
        session,
        setup.tenant_id,
        setup.item_id,
        setup.bin_id,
        Decimal(quantity),
        unit_cost=Decimal(unit_cost),
    )
