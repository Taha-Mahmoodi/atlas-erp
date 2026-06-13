"""Return (RMA) service behaviour (PLAN 7.4, D-046): create a return against an invoiced order,
over-return rejection, post → an inventory RECEIPT move (on-hand UP) reversing COGS (Dr Inventory /
Cr COGS) AND an AR credit note (Dr Revenue / Cr AR), returned_quantity raised, docflow,
closed-period rollback, idempotency, cancel — and the headline end-to-end O2C-nets-to-zero proof.

Returns go through the REAL service inside a uow (D-025); the sales conftest's autouse fixture
registers the sales→inventory (RECEIPT) + sales→finance (credit note) handlers, so a posted return
moves stock and posts the credit note exactly as in production. Per issue #53 the rejection cases
use
create-time 422s and the happy path asserts success + state (the 7.3 test_deliveries.py pattern).
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
from app.modules.finance.models import CustomerInvoice, JournalEntry, JournalLine
from app.modules.inventory import queries as inventory_queries
from app.modules.sales import queries as sales_queries
from app.modules.sales import service
from app.modules.sales.constants import (
    ORDER_RETURNED_BY_RETURN_LINK,
    RETURN_CREDITED_BY_CREDIT_NOTE_LINK,
    RETURN_RECEIVED_BY_STOCK_MOVE_LINK,
    ReturnStatus,
    SalesOrderStatus,
)
from app.modules.sales.schemas import BillingLineCreate, ReturnLineCreate
from tests.modules.sales.factories import (
    BillingSetup,
    build_billing,
    build_billing_setup,
    build_delivered_order,
    build_return,
    post_billing,
    post_return,
)


async def _order_line_id(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> uuid.UUID:
    with tenant_context(tenant_id):
        lines = await service.get_sales_order_lines(session, tenant_id, order_id)
    return lines[0].id


def _rline(order_line_id: uuid.UUID, bin_id: uuid.UUID, qty: str, **kw: object) -> ReturnLineCreate:
    return ReturnLineCreate(
        sales_order_line_id=order_line_id,
        bin_id=bin_id,
        quantity=Decimal(qty),
        **kw,  # type: ignore[arg-type]
    )


async def _journal_lines_for_type(
    session: AsyncSession, tenant_id: uuid.UUID, doc_type: str
) -> list[JournalLine]:
    with tenant_context(tenant_id):
        entries = (
            await session.execute(
                select(JournalEntry).where(
                    JournalEntry.tenant_id == tenant_id,
                    JournalEntry.document_type == doc_type,
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


async def _on_hand(session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID) -> Decimal:
    with tenant_context(tenant_id):
        return await inventory_queries.total_on_hand(session, tenant_id, item_id)


async def _build_invoiced_order(
    session: AsyncSession,
    setup: BillingSetup,
    *,
    quantity: str = "5",
    unit_price: str = "10",
    unit_cost: str = "4",
    tax_code_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create → deliver → fully bill (post) an order: the return precondition (delivered AND
    invoiced). Returns (order_id, order_line_id)."""
    order = await build_delivered_order(
        session, setup, quantity=quantity, unit_price=unit_price,
        unit_cost=unit_cost, tax_code_id=tax_code_id,
    )
    line_id = await _order_line_id(session, setup.order.tenant_id, order.id)
    billing = await build_billing(
        session, setup, order_id=order.id, lines=[BillingLineCreate(
            sales_order_line_id=line_id, quantity=Decimal(quantity)
        )],
    )
    await post_billing(session, setup.order.tenant_id, billing.id)
    return order.id, line_id


@pytest.fixture
async def billing_setup(db_session: AsyncSession, tenant_a: uuid.UUID) -> BillingSetup:
    return await build_billing_setup(db_session, tenant_a)


# --- Create draft -------------------------------------------------------------


async def test_create_return_is_draft_with_rma_number(
    db_session: AsyncSession, billing_setup: BillingSetup
) -> None:
    """A created return is DRAFT, carries an RMA number, snapshots the customer."""
    setup = billing_setup
    order_id, line_id = await _build_invoiced_order(db_session, setup, quantity="5")
    sales_return = await build_return(
        db_session, setup, order_id=order_id, lines=[_rline(line_id, setup.order.bin_id, "2")]
    )
    assert sales_return.status == ReturnStatus.DRAFT.value
    assert sales_return.return_number.startswith("RMA-")
    assert sales_return.customer_id == setup.order.customer_id
    assert Decimal(sales_return.total_amount) == Decimal(20)  # 2 @ 10


async def test_create_rejects_over_return(
    db_session: AsyncSession, billing_setup: BillingSetup
) -> None:
    """Returning more than invoiced-not-returned → 422 sales.over_return."""
    setup = billing_setup
    order_id, line_id = await _build_invoiced_order(db_session, setup, quantity="5")
    with pytest.raises(ValidationFailedError) as exc:
        await build_return(
            db_session, setup, order_id=order_id,
            lines=[_rline(line_id, setup.order.bin_id, "6")],  # invoiced 5
        )
    assert exc.value.code == "sales.over_return"


# --- Post: stock receipt reversing COGS + credit note -------------------------


async def test_post_receives_stock_reversing_cogs(
    db_session: AsyncSession, billing_setup: BillingSetup
) -> None:
    """Posting a return RECEIVES stock back (on-hand UP) with a Dr Inventory / Cr COGS journal at
    the
    book cost — reversing the delivery's issue (D-046)."""
    setup = billing_setup
    # deliver 5 @ cost 4 (issued 5, on-hand 5 left of the seeded 10); bill 5; then return 2.
    order_id, line_id = await _build_invoiced_order(
        db_session, setup, quantity="5", unit_cost="4"
    )
    on_hand_before = await _on_hand(db_session, setup.order.tenant_id, setup.order.item_id)
    sales_return = await build_return(
        db_session, setup, order_id=order_id, lines=[_rline(line_id, setup.order.bin_id, "2")]
    )
    posted = await post_return(db_session, setup.order.tenant_id, sales_return.id)
    assert posted.status == ReturnStatus.POSTED.value

    on_hand_after = await _on_hand(db_session, setup.order.tenant_id, setup.order.item_id)
    assert on_hand_after == on_hand_before + Decimal(2)  # goods back in

    # The return's COGS entry reverses the issue: Dr Inventory 8 / Cr COGS 8 (2 @ 4) — exactly the
    # opposite direction of the delivery's Dr COGS / Cr Inventory. The COGS account's NET debit over
    # all COGS entries = 20 (delivery, 5 @ 4) − 8 (return, 2 @ 4) = 12; the credit/debit on the
    # return entry alone proves the reversal direction.
    return_cogs = await _journal_lines_for_type(
        db_session, setup.order.tenant_id, DocumentType.COGS.value
    )
    cogs_net = _debit(return_cogs, setup.order.cogs_account_id) - _credit(
        return_cogs, setup.order.cogs_account_id
    )
    assert cogs_net == Decimal(12)
    # The return credited COGS by 8 (the reversal leg).
    assert _credit(return_cogs, setup.order.cogs_account_id) == Decimal(8)
    assert _debit(return_cogs, setup.order.inventory_account_id) >= Decimal(8)


async def test_post_creates_credit_note_dr_revenue_cr_ar(
    db_session: AsyncSession, billing_setup: BillingSetup
) -> None:
    """Posting a return creates a POSTED AR credit note: Dr revenue / Cr AR at the credit net,
    reversing the billing's revenue + AR (D-046)."""
    setup = billing_setup
    order_id, line_id = await _build_invoiced_order(db_session, setup, quantity="5")
    sales_return = await build_return(
        db_session, setup, order_id=order_id, lines=[_rline(line_id, setup.order.bin_id, "2")]
    )
    await post_return(db_session, setup.order.tenant_id, sales_return.id)

    cn_lines = await _journal_lines_for_type(
        db_session, setup.order.tenant_id, DocumentType.AR_CREDIT_NOTE.value
    )
    assert _debit(cn_lines, setup.revenue_account_id) == Decimal(20)  # 2 @ 10 revenue reversed
    assert _credit(cn_lines, setup.ar_account_id) == Decimal(20)  # AR reduced

    # A credit-note CustomerInvoice row exists, numbered CN-, open_amount 0.
    with tenant_context(setup.order.tenant_id):
        notes = (
            await db_session.execute(
                select(CustomerInvoice).where(
                    CustomerInvoice.tenant_id == setup.order.tenant_id,
                    CustomerInvoice.invoice_number.like("CN-%"),
                )
            )
        ).scalars().all()
    assert len(notes) == 1
    assert Decimal(notes[0].open_amount) == Decimal(0)


async def test_post_raises_returned_quantity(
    db_session: AsyncSession, billing_setup: BillingSetup
) -> None:
    """A post raises the order line's returned_quantity; open-to-return shrinks by the returned
    amount."""
    setup = billing_setup
    order_id, line_id = await _build_invoiced_order(db_session, setup, quantity="5")
    sales_return = await build_return(
        db_session, setup, order_id=order_id, lines=[_rline(line_id, setup.order.bin_id, "2")]
    )
    await post_return(db_session, setup.order.tenant_id, sales_return.id)
    with tenant_context(setup.order.tenant_id):
        open_ret = await sales_queries.so_line_open_to_return(
            db_session, setup.order.tenant_id, line_id
        )
    assert open_ret == Decimal(3)  # invoiced 5 - returned 2


async def test_post_links_docflow(
    db_session: AsyncSession, billing_setup: BillingSetup
) -> None:
    """The docflow chain links order → return (returned_by), return → move (received_by) and return
    →
    credit note (credited_by) after a post."""
    setup = billing_setup
    order_id, line_id = await _build_invoiced_order(db_session, setup, quantity="5")
    sales_return = await build_return(
        db_session, setup, order_id=order_id, lines=[_rline(line_id, setup.order.bin_id, "2")]
    )
    await post_return(db_session, setup.order.tenant_id, sales_return.id)
    with tenant_context(setup.order.tenant_id):
        reloaded = await service.get_return(db_session, setup.order.tenant_id, sales_return.id)
        chain = await docflow.get_document_chain(
            db_session, setup.order.tenant_id, reloaded.document_id
        )
    link_types = {edge.link_type for edge in chain.edges}
    assert ORDER_RETURNED_BY_RETURN_LINK in link_types
    assert RETURN_RECEIVED_BY_STOCK_MOVE_LINK in link_types
    assert RETURN_CREDITED_BY_CREDIT_NOTE_LINK in link_types


async def test_post_is_idempotent_reject(
    db_session: AsyncSession, billing_setup: BillingSetup
) -> None:
    """Re-posting a POSTED return is rejected (a posted return is terminal)."""
    setup = billing_setup
    order_id, line_id = await _build_invoiced_order(db_session, setup, quantity="5")
    sales_return = await build_return(
        db_session, setup, order_id=order_id, lines=[_rline(line_id, setup.order.bin_id, "2")]
    )
    await post_return(db_session, setup.order.tenant_id, sales_return.id)
    with pytest.raises(ConflictError) as exc:
        await post_return(db_session, setup.order.tenant_id, sales_return.id)
    assert exc.value.code == "sales.return_already_posted"


async def test_cancel_draft_only(
    db_session: AsyncSession, billing_setup: BillingSetup
) -> None:
    """A DRAFT return cancels; a POSTED return is terminal (cannot be cancelled)."""
    setup = billing_setup
    order_id, line_id = await _build_invoiced_order(db_session, setup, quantity="5")
    r1 = await build_return(
        db_session, setup, order_id=order_id, lines=[_rline(line_id, setup.order.bin_id, "1")]
    )

    from app.core.events import run_in_uow

    async def _cancel(rid: uuid.UUID) -> None:
        async def work() -> None:
            with tenant_context(setup.order.tenant_id):
                await service.cancel_return(db_session, setup.order.tenant_id, rid)

        with tenant_context(setup.order.tenant_id):
            await run_in_uow(db_session, work)

    await _cancel(r1.id)
    with tenant_context(setup.order.tenant_id):
        reloaded = await service.get_return(db_session, setup.order.tenant_id, r1.id)
    assert reloaded.status == ReturnStatus.CANCELLED.value

    r2 = await build_return(
        db_session, setup, order_id=order_id, lines=[_rline(line_id, setup.order.bin_id, "1")]
    )
    await post_return(db_session, setup.order.tenant_id, r2.id)
    with pytest.raises(ConflictError) as exc:
        await _cancel(r2.id)
    assert exc.value.code == "sales.return_not_cancellable"


async def test_post_closed_period_rolls_back(
    db_session: AsyncSession, billing_setup: BillingSetup
) -> None:
    """A return dated into a CLOSED period trips a move's / the credit note's journal trigger and
    rolls the WHOLE post back — return still DRAFT, no credit note (D-046 all-or-nothing)."""
    setup = billing_setup
    order_id, line_id = await _build_invoiced_order(db_session, setup, quantity="5")
    from app.core.events import run_in_uow
    from app.modules.sales.schemas import ReturnCreate

    async def _create_march() -> uuid.UUID:
        holder: dict[str, uuid.UUID] = {}

        async def work() -> None:
            with tenant_context(setup.order.tenant_id):
                sales_return = await service.create_return(
                    db_session,
                    setup.order.tenant_id,
                    ReturnCreate(
                        sales_order_id=order_id,
                        warehouse_id=setup.order.warehouse_id,
                        return_date=date(2026, 3, 15),
                        lines=[_rline(line_id, setup.order.bin_id, "2")],
                    ),
                )
                holder["id"] = sales_return.id

        with tenant_context(setup.order.tenant_id):
            await run_in_uow(db_session, work)
        return holder["id"]

    return_id = await _create_march()
    on_hand_before = await _on_hand(db_session, setup.order.tenant_id, setup.order.item_id)
    with tenant_context(setup.order.tenant_id):
        period = await finance_queries.find_period_for_date(
            db_session, setup.order.tenant_id, date(2026, 3, 15)
        )
        await finance_service.close_period(db_session, setup.order.tenant_id, period.id)
        await db_session.commit()

    with pytest.raises(Exception):  # noqa: B017 - period trigger / service error
        await post_return(db_session, setup.order.tenant_id, return_id)

    on_hand_after = await _on_hand(db_session, setup.order.tenant_id, setup.order.item_id)
    assert on_hand_after == on_hand_before  # nothing received
    with tenant_context(setup.order.tenant_id):
        reloaded = await service.get_return(db_session, setup.order.tenant_id, return_id)
    assert reloaded.status == ReturnStatus.DRAFT.value


# --- The headline end-to-end O2C-nets-to-zero proof ---------------------------


async def test_full_o2c_loop_nets_to_zero(
    db_session: AsyncSession, billing_setup: BillingSetup
) -> None:
    """The headline proof (D-046): order → confirm → deliver (Dr COGS / Cr Inv) → bill (Dr AR / Cr
    Rev) leaves AR + revenue recognized, inventory down and COGS up; then a FULL return reverses
    every
    leg (inventory back UP, COGS back DOWN, revenue back DOWN, AR back DOWN) so the AR, revenue and
    COGS accounts net to ZERO and on-hand returns to its post-seed level (the goods are physically
    back in stock, so the inventory ACCOUNT holds their value again, not zero). Asserted via the
    finance account-balance projection (the 6.4 GR/IR-clears-to-zero mirror)."""
    setup = billing_setup
    tenant_id = setup.order.tenant_id
    # Seeded on-hand is 5 (deliver consumes all 5 → on-hand 0 after delivery); deliver+bill 5, then
    # return all 5 → on-hand back to 5, the goods physically returned.
    order_id, line_id = await _build_invoiced_order(
        db_session, setup, quantity="5", unit_price="10", unit_cost="4"
    )
    on_hand_after_delivery = await _on_hand(db_session, tenant_id, setup.order.item_id)
    assert on_hand_after_delivery == Decimal(0)

    sales_return = await build_return(
        db_session, setup, order_id=order_id, lines=[_rline(line_id, setup.order.bin_id, "5")]
    )
    await post_return(db_session, tenant_id, sales_return.id)

    # On-hand back up by the full returned quantity (the 5 issued are received back).
    on_hand_final = await _on_hand(db_session, tenant_id, setup.order.item_id)
    assert on_hand_final == Decimal(5)

    # The account-balance projection: the P&L + receivable accounts (AR, revenue, COGS) net to ZERO
    # after the full return reverses the billing + delivery — the order-to-cash loop closed cleanly.
    # Inventory holds the returned goods' value (5 @ 4 = 20), NOT zero — the goods are back in
    # stock.
    with tenant_context(tenant_id):
        balances = await finance_queries.account_balances(
            db_session, tenant_id, date_to=date(2026, 12, 31)
        )
    assert balances.get(setup.ar_account_id, Decimal(0)) == Decimal(0)
    assert balances.get(setup.revenue_account_id, Decimal(0)) == Decimal(0)
    assert balances.get(setup.order.cogs_account_id, Decimal(0)) == Decimal(0)
    assert balances.get(setup.order.inventory_account_id, Decimal(0)) == Decimal(20)

    # The order is fully returned: open-to-return is 0.
    with tenant_context(tenant_id):
        open_ret = await sales_queries.so_line_open_to_return(db_session, tenant_id, line_id)
    assert open_ret == Decimal(0)
    # Sanity: the order had advanced to CLOSED at full billing.
    with tenant_context(tenant_id):
        order = await service.get_sales_order(db_session, tenant_id, order_id)
    assert order.status == SalesOrderStatus.CLOSED.value
