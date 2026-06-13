"""Billing service behaviour (PLAN 7.4, D-046): create a billing from a delivered order,
over-billing
rejection, post → the finance AR customer invoice (Dr AR / Cr Revenue + tax), invoiced_quantity
raised + order advanced INVOICED/CLOSED, docflow order→delivery→billing→invoice, closed-period
rollback, idempotency, cancel, and the bill_all_delivered convenience path.

Billings go through the REAL service inside a uow (D-025); the sales conftest's autouse fixture
registers the sales→finance billing handler, so a posted billing creates + posts the AR invoice
exactly as in production. Per issue #53 the rejection cases use create-time 422s and the happy path
asserts success + advanced state (the 7.3 test_deliveries.py pattern).
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
from app.modules.sales import service
from app.modules.sales.constants import (
    BILLING_INVOICED_BY_INVOICE_LINK,
    ORDER_BILLED_BY_BILLING_LINK,
    ORDER_DELIVERED_BY_DELIVERY_LINK,
    BillingStatus,
    SalesOrderStatus,
)
from app.modules.sales.schemas import BillingLineCreate
from tests.modules.sales.factories import (
    BillingSetup,
    build_billing,
    build_billing_setup,
    build_delivered_order,
    post_billing,
)


async def _order_line_id(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> uuid.UUID:
    with tenant_context(tenant_id):
        lines = await service.get_sales_order_lines(session, tenant_id, order_id)
    return lines[0].id


def _line(order_line_id: uuid.UUID, qty: str, **kw: object) -> BillingLineCreate:
    return BillingLineCreate(
        sales_order_line_id=order_line_id, quantity=Decimal(qty), **kw  # type: ignore[arg-type]
    )


async def _ar_journal_lines(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[JournalLine]:
    with tenant_context(tenant_id):
        entries = (
            await session.execute(
                select(JournalEntry).where(
                    JournalEntry.tenant_id == tenant_id,
                    JournalEntry.document_type == DocumentType.AR_INVOICE.value,
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
async def billing_setup(db_session: AsyncSession, tenant_a: uuid.UUID) -> BillingSetup:
    return await build_billing_setup(db_session, tenant_a)


# --- Create draft -------------------------------------------------------------


async def test_create_billing_is_draft_with_bil_number(
    db_session: AsyncSession, billing_setup: BillingSetup
) -> None:
    """A created billing is DRAFT, carries a BIL number, snapshots the customer + terms."""
    order = await build_delivered_order(db_session, billing_setup, quantity="5")
    line_id = await _order_line_id(db_session, billing_setup.order.tenant_id, order.id)
    billing = await build_billing(
        db_session, billing_setup, order_id=order.id, lines=[_line(line_id, "3")]
    )
    assert billing.status == BillingStatus.DRAFT.value
    assert billing.billing_number.startswith("BIL-")
    assert billing.customer_id == billing_setup.order.customer_id
    assert Decimal(billing.total_amount) == Decimal(30)  # 3 @ 10


async def test_create_rejects_over_billing(
    db_session: AsyncSession, billing_setup: BillingSetup
) -> None:
    """Billing more than delivered-not-invoiced → 422 sales.over_billing."""
    order = await build_delivered_order(db_session, billing_setup, quantity="5")
    line_id = await _order_line_id(db_session, billing_setup.order.tenant_id, order.id)
    with pytest.raises(ValidationFailedError) as exc:
        await build_billing(
            db_session, billing_setup, order_id=order.id, lines=[_line(line_id, "6")]  # del 5
        )
    assert exc.value.code == "sales.over_billing"


async def test_create_rejects_undelivered_order(
    db_session: AsyncSession, billing_setup: BillingSetup
) -> None:
    """An order with nothing delivered cannot be billed → 422 sales.order_not_delivered."""
    from tests.modules.sales.factories import (
        build_sales_order,
        build_stock_for_cost,
        confirm_sales_order,
    )

    await build_stock_for_cost(db_session, billing_setup.order, "10", unit_cost="4")
    order = await build_sales_order(
        db_session,
        billing_setup.order.tenant_id,
        customer_id=billing_setup.order.customer_id,
        item_id=billing_setup.order.item_id,
        uom_id=billing_setup.order.uom_id,
        quantity="5",
    )
    confirmed = await confirm_sales_order(db_session, billing_setup.order.tenant_id, order.id)
    line_id = await _order_line_id(db_session, billing_setup.order.tenant_id, confirmed.id)
    with pytest.raises(ValidationFailedError) as exc:
        await build_billing(
            db_session, billing_setup, order_id=confirmed.id, lines=[_line(line_id, "3")]
        )
    assert exc.value.code == "sales.order_not_delivered"


# --- Post: the AR invoice -----------------------------------------------------


async def test_post_creates_ar_invoice_dr_ar_cr_revenue(
    db_session: AsyncSession, billing_setup: BillingSetup
) -> None:
    """Posting a billing creates a POSTED AR customer invoice via the event bus: Dr AR control / Cr
    sales revenue at the billed net (no tax → gross == net)."""
    setup = billing_setup
    order = await build_delivered_order(db_session, setup, quantity="5", unit_price="10")
    line_id = await _order_line_id(db_session, setup.order.tenant_id, order.id)
    billing = await build_billing(
        db_session, setup, order_id=order.id, lines=[_line(line_id, "3")]
    )
    posted = await post_billing(db_session, setup.order.tenant_id, billing.id)
    assert posted.status == BillingStatus.POSTED.value
    assert posted.posted_at is not None

    with tenant_context(setup.order.tenant_id):
        invoices = (
            await db_session.execute(
                select(CustomerInvoice).where(
                    CustomerInvoice.tenant_id == setup.order.tenant_id
                )
            )
        ).scalars().all()
    assert len(invoices) == 1
    assert invoices[0].invoice_number is not None
    assert Decimal(invoices[0].gross_amount) == Decimal(30)

    lines = await _ar_journal_lines(db_session, setup.order.tenant_id)
    assert _debit(lines, setup.ar_account_id) == Decimal(30)
    assert _credit(lines, setup.revenue_account_id) == Decimal(30)


async def test_post_with_tax_posts_output_tax(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A billing whose order line carries a 10% tax code posts Cr output tax: Dr AR 33 / Cr Rev 30 /
    Cr Tax 3."""
    setup = await build_billing_setup(db_session, tenant_a, tax_rate="10")
    order = await build_delivered_order(
        db_session, setup, quantity="5", unit_price="10", tax_code_id=setup.tax_code_id
    )
    line_id = await _order_line_id(db_session, setup.order.tenant_id, order.id)
    billing = await build_billing(
        db_session, setup, order_id=order.id, lines=[_line(line_id, "3", tax_code_id=None)]
    )
    await post_billing(db_session, setup.order.tenant_id, billing.id)
    lines = await _ar_journal_lines(db_session, setup.order.tenant_id)
    assert _debit(lines, setup.ar_account_id) == Decimal(33)
    assert _credit(lines, setup.revenue_account_id) == Decimal(30)
    assert _credit(lines, setup.tax_account_id) == Decimal(3)


async def test_post_raises_invoiced_quantity_and_advances_order(
    db_session: AsyncSession, billing_setup: BillingSetup
) -> None:
    """A partial billing raises invoiced_quantity + leaves the order DELIVERED (more to invoice); a
    second billing completes it → order CLOSED (fully delivered AND invoiced)."""
    setup = billing_setup
    order = await build_delivered_order(db_session, setup, quantity="5")
    line_id = await _order_line_id(db_session, setup.order.tenant_id, order.id)

    b1 = await build_billing(db_session, setup, order_id=order.id, lines=[_line(line_id, "2")])
    await post_billing(db_session, setup.order.tenant_id, b1.id)
    from app.modules.sales import queries as sales_queries

    with tenant_context(setup.order.tenant_id):
        reloaded = await service.get_sales_order(db_session, setup.order.tenant_id, order.id)
        assert reloaded.status == SalesOrderStatus.DELIVERED.value
        # open-to-invoice = delivered(5) - invoiced(2) = 3
        open_inv = await sales_queries.so_line_open_to_invoice(
            db_session, setup.order.tenant_id, line_id
        )
    assert open_inv == Decimal(3)

    b2 = await build_billing(db_session, setup, order_id=order.id, lines=[_line(line_id, "3")])
    await post_billing(db_session, setup.order.tenant_id, b2.id)
    with tenant_context(setup.order.tenant_id):
        reloaded = await service.get_sales_order(db_session, setup.order.tenant_id, order.id)
    assert reloaded.status == SalesOrderStatus.CLOSED.value


async def test_bill_all_delivered_convenience(
    db_session: AsyncSession, billing_setup: BillingSetup
) -> None:
    """bill_all_delivered bills the full delivered-not-invoiced quantity in one shot → CLOSED."""
    setup = billing_setup
    order = await build_delivered_order(db_session, setup, quantity="5")
    billing = await build_billing(
        db_session, setup, order_id=order.id, lines=[], bill_all_delivered=True
    )
    assert Decimal(billing.total_amount) == Decimal(50)  # 5 @ 10
    await post_billing(db_session, setup.order.tenant_id, billing.id)
    with tenant_context(setup.order.tenant_id):
        reloaded = await service.get_sales_order(db_session, setup.order.tenant_id, order.id)
    assert reloaded.status == SalesOrderStatus.CLOSED.value


async def test_post_links_docflow_order_delivery_billing_invoice(
    db_session: AsyncSession, billing_setup: BillingSetup
) -> None:
    """The docflow chain links order → delivery (delivered_by), order → billing (billed_by), and
    billing → AR invoice (invoiced_by_invoice) after a post."""
    setup = billing_setup
    order = await build_delivered_order(db_session, setup, quantity="5")
    line_id = await _order_line_id(db_session, setup.order.tenant_id, order.id)
    billing = await build_billing(
        db_session, setup, order_id=order.id, lines=[_line(line_id, "5")]
    )
    await post_billing(db_session, setup.order.tenant_id, billing.id)
    with tenant_context(setup.order.tenant_id):
        reloaded = await service.get_billing(db_session, setup.order.tenant_id, billing.id)
        order_doc = (
            await service.get_sales_order(db_session, setup.order.tenant_id, order.id)
        ).document_id
        order_chain = await docflow.get_document_chain(
            db_session, setup.order.tenant_id, order_doc
        )
        billing_chain = await docflow.get_document_chain(
            db_session, setup.order.tenant_id, reloaded.document_id
        )
    order_links = {edge.link_type for edge in order_chain.edges}
    billing_links = {edge.link_type for edge in billing_chain.edges}
    assert ORDER_DELIVERED_BY_DELIVERY_LINK in order_links
    assert ORDER_BILLED_BY_BILLING_LINK in order_links
    assert BILLING_INVOICED_BY_INVOICE_LINK in billing_links


async def test_post_closed_period_rolls_back(
    db_session: AsyncSession, billing_setup: BillingSetup
) -> None:
    """A billing dated into a CLOSED period trips the AR invoice's journal period trigger and rolls
    the WHOLE post back — billing still DRAFT, no AR invoice (D-046 all-or-nothing)."""
    setup = billing_setup
    order = await build_delivered_order(db_session, setup, quantity="5")
    line_id = await _order_line_id(db_session, setup.order.tenant_id, order.id)
    # Bill dated into March, then close March.
    from app.core.events import run_in_uow
    from app.modules.sales.schemas import BillingCreate

    async def _create_march() -> uuid.UUID:
        holder: dict[str, uuid.UUID] = {}

        async def work() -> None:
            with tenant_context(setup.order.tenant_id):
                billing = await service.create_billing(
                    db_session,
                    setup.order.tenant_id,
                    BillingCreate(
                        sales_order_id=order.id,
                        billing_date=date(2026, 3, 15),
                        lines=[_line(line_id, "3")],
                    ),
                )
                holder["id"] = billing.id

        with tenant_context(setup.order.tenant_id):
            await run_in_uow(db_session, work)
        return holder["id"]

    billing_id = await _create_march()
    with tenant_context(setup.order.tenant_id):
        period = await finance_queries.find_period_for_date(
            db_session, setup.order.tenant_id, date(2026, 3, 15)
        )
        await finance_service.close_period(db_session, setup.order.tenant_id, period.id)
        await db_session.commit()

    with pytest.raises(Exception):  # noqa: B017 - period trigger / service error
        await post_billing(db_session, setup.order.tenant_id, billing_id)

    with tenant_context(setup.order.tenant_id):
        reloaded = await service.get_billing(db_session, setup.order.tenant_id, billing_id)
        invoices = (
            await db_session.execute(
                select(CustomerInvoice).where(
                    CustomerInvoice.tenant_id == setup.order.tenant_id
                )
            )
        ).scalars().all()
    assert reloaded.status == BillingStatus.DRAFT.value
    assert len(invoices) == 0


async def test_post_is_idempotent_reject(
    db_session: AsyncSession, billing_setup: BillingSetup
) -> None:
    """Re-posting a POSTED billing is rejected (a posted billing is terminal)."""
    setup = billing_setup
    order = await build_delivered_order(db_session, setup, quantity="5")
    line_id = await _order_line_id(db_session, setup.order.tenant_id, order.id)
    billing = await build_billing(
        db_session, setup, order_id=order.id, lines=[_line(line_id, "3")]
    )
    await post_billing(db_session, setup.order.tenant_id, billing.id)
    with pytest.raises(ConflictError) as exc:
        await post_billing(db_session, setup.order.tenant_id, billing.id)
    assert exc.value.code == "sales.billing_already_posted"


async def test_cancel_draft_only(
    db_session: AsyncSession, billing_setup: BillingSetup
) -> None:
    """A DRAFT billing cancels; a POSTED billing is terminal (cannot be cancelled)."""
    setup = billing_setup
    order = await build_delivered_order(db_session, setup, quantity="5")
    line_id = await _order_line_id(db_session, setup.order.tenant_id, order.id)
    b1 = await build_billing(db_session, setup, order_id=order.id, lines=[_line(line_id, "2")])

    from app.core.events import run_in_uow

    async def _cancel(bid: uuid.UUID) -> None:
        async def work() -> None:
            with tenant_context(setup.order.tenant_id):
                await service.cancel_billing(db_session, setup.order.tenant_id, bid)

        with tenant_context(setup.order.tenant_id):
            await run_in_uow(db_session, work)

    await _cancel(b1.id)
    with tenant_context(setup.order.tenant_id):
        reloaded = await service.get_billing(db_session, setup.order.tenant_id, b1.id)
    assert reloaded.status == BillingStatus.CANCELLED.value

    b2 = await build_billing(db_session, setup, order_id=order.id, lines=[_line(line_id, "2")])
    await post_billing(db_session, setup.order.tenant_id, b2.id)
    with pytest.raises(ConflictError) as exc:
        await _cancel(b2.id)
    assert exc.value.code == "sales.billing_not_cancellable"
