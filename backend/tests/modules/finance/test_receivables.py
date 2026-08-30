"""Accounts Receivable service + API behaviour (PLAN 4.6, D-029), SQLite.

Proves the invoice -> post -> receipt flow, open-item clearing, the aging projection, dunning level
advancement, idempotent posting/receipt, RBAC, and tenant isolation — all single-functional-currency
here. Realized FX at clearing (D-019) is proven separately in test_receivables_fx.py. The AP suite
(test_payables.py) mirror with the sign flipped, plus the AR-only dunning tests.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow, subscribe
from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.finance import queries, service
from app.modules.finance.constants import (
    AR_PARTNER_TYPE,
    InvoiceStatus,
    ReceiptStatus,
)
from app.modules.finance.events import CustomerInvoicePosted, CustomerReceiptPosted
from app.modules.finance.models import (
    CustomerInvoice,
    CustomerReceiptAllocation,
    JournalLine,
)
from app.modules.finance.receivables_schemas import (
    CustomerInvoiceCreate,
    CustomerInvoiceLineCreate,
    CustomerReceiptCreate,
    ReceiptAllocationCreate,
)
from tests.modules.finance.conftest import ArSetup
from tests.modules.finance.factories import seed_advance_account

_INVOICE_DATE = date(2026, 3, 1)
_DUE_DATE = date(2026, 3, 31)
_RECEIPT_DATE = date(2026, 3, 15)


def _invoice_payload(
    setup: ArSetup,
    *,
    net: str = "100.00",
    with_tax: bool = False,
    partner_id: uuid.UUID | None = None,
    partner_name: str = "Globex Inc",
    due_date: date = _DUE_DATE,
) -> CustomerInvoiceCreate:
    return CustomerInvoiceCreate(
        partner_id=partner_id or uuid.uuid4(),
        partner_name=partner_name,
        invoice_date=_INVOICE_DATE,
        due_date=due_date,
        currency_code="USD",
        ar_account_id=setup.accounts["1200"],
        description="Consulting services",
        lines=[
            CustomerInvoiceLineCreate(
                account_id=setup.accounts["4000"],
                net_amount=Decimal(net),
                tax_code_id=setup.tax_code_id if with_tax else None,
            )
        ],
    )


async def _create_and_post_invoice(
    session: AsyncSession,
    setup: ArSetup,
    payload: CustomerInvoiceCreate,
) -> CustomerInvoice:
    with tenant_context(setup.tenant_id):
        invoice = await service.create_customer_invoice(session, setup.tenant_id, payload)
        await session.commit()

        async def work() -> None:
            await service.post_customer_invoice(session, setup.tenant_id, invoice.id)

        await run_in_uow(session, work)
        await session.refresh(invoice)
    return invoice


# --- invoice create + post ----------------------------------------------------


async def test_post_invoice_builds_balanced_journal(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    captured: list[CustomerInvoicePosted] = []

    async def _capture(_s: AsyncSession, event: CustomerInvoicePosted) -> None:
        captured.append(event)

    subscribe(CustomerInvoicePosted.key, _capture)
    invoice = await _create_and_post_invoice(db_session, ar_setup, _invoice_payload(ar_setup))

    assert invoice.status == InvoiceStatus.POSTED.value
    assert invoice.invoice_number == "INV-2026-00001"
    assert invoice.journal_entry_id is not None
    assert Decimal(str(invoice.open_amount)) == Decimal("100.00")
    assert Decimal(str(invoice.gross_amount)) == Decimal("100.00")

    with tenant_context(ar_setup.tenant_id):
        lines = (
            await db_session.execute(
                select(JournalLine).where(JournalLine.journal_entry_id == invoice.journal_entry_id)
            )
        ).scalars().all()
    debit = sum((Decimal(str(line.functional_debit_amount)) for line in lines), Decimal(0))
    credit = sum((Decimal(str(line.functional_credit_amount)) for line in lines), Decimal(0))
    assert debit == credit == Decimal("100.00")
    # The AR control line is DEBITED for the gross and carries the opaque partner_id (D-029).
    ar_line = next(line for line in lines if line.account_id == ar_setup.accounts["1200"])
    assert Decimal(str(ar_line.transaction_debit_amount)) == Decimal("100.00")
    assert ar_line.partner_id == invoice.partner_id
    assert ar_line.partner_type == AR_PARTNER_TYPE
    # Revenue line is CREDITED.
    rev_line = next(line for line in lines if line.account_id == ar_setup.accounts["4000"])
    assert Decimal(str(rev_line.transaction_credit_amount)) == Decimal("100.00")
    # Event fired with the invoice totals.
    assert len(captured) == 1
    assert captured[0].invoice_id == invoice.id
    assert captured[0].gross_amount == Decimal("100.00")


async def test_post_invoice_with_tax_posts_output_tax(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    invoice = await _create_and_post_invoice(
        db_session, ar_setup, _invoice_payload(ar_setup, net="100.00", with_tax=True)
    )
    # gross = net + tax = 100 + 20.
    assert Decimal(str(invoice.net_amount)) == Decimal("100.00")
    assert Decimal(str(invoice.tax_amount)) == Decimal("20.00")
    assert Decimal(str(invoice.gross_amount)) == Decimal("120.00")
    assert Decimal(str(invoice.open_amount)) == Decimal("120.00")

    with tenant_context(ar_setup.tenant_id):
        lines = (
            await db_session.execute(
                select(JournalLine).where(JournalLine.journal_entry_id == invoice.journal_entry_id)
            )
        ).scalars().all()
    # Output tax is CREDITED to the tax code's payable account (2200).
    tax_line = next(line for line in lines if line.account_id == ar_setup.accounts["2200"])
    assert Decimal(str(tax_line.transaction_credit_amount)) == Decimal("20.00")
    ar_line = next(line for line in lines if line.account_id == ar_setup.accounts["1200"])
    assert Decimal(str(ar_line.transaction_debit_amount)) == Decimal("120.00")


async def test_create_invoice_requires_lines(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    payload = _invoice_payload(ar_setup)
    payload.lines = []
    with tenant_context(ar_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_customer_invoice(db_session, ar_setup.tenant_id, payload)
    assert exc.value.code == "finance.customer_invoice_no_lines"


# --- receipt clearing ---------------------------------------------------------


async def _receive_invoice(
    session: AsyncSession,
    setup: ArSetup,
    invoice: CustomerInvoice,
    amount: str,
) -> uuid.UUID:
    captured: list[CustomerReceiptPosted] = []

    async def _capture(_s: AsyncSession, event: CustomerReceiptPosted) -> None:
        captured.append(event)

    subscribe(CustomerReceiptPosted.key, _capture)
    holder: dict[str, uuid.UUID] = {}
    with tenant_context(setup.tenant_id):
        async def work() -> None:
            receipt = await service.create_and_post_receipt(
                session,
                setup.tenant_id,
                CustomerReceiptCreate(
                    partner_id=invoice.partner_id,
                    partner_name=invoice.partner_name,
                    receipt_date=_RECEIPT_DATE,
                    currency_code="USD",
                    bank_account_id=setup.accounts["1000"],
                    amount=Decimal(amount),
                    allocations=[
                        ReceiptAllocationCreate(invoice_id=invoice.id, amount=Decimal(amount))
                    ],
                ),
            )
            holder["id"] = receipt.id

        await run_in_uow(session, work)
        await session.refresh(invoice)
    assert len(captured) == 1
    return holder["id"]


async def test_full_receipt_clears_invoice(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    invoice = await _create_and_post_invoice(db_session, ar_setup, _invoice_payload(ar_setup))
    receipt_id = await _receive_invoice(db_session, ar_setup, invoice, "100.00")

    assert invoice.status == InvoiceStatus.PAID.value
    assert Decimal(str(invoice.open_amount)) == Decimal("0.00")

    with tenant_context(ar_setup.tenant_id):
        allocations = (
            await db_session.execute(
                select(CustomerReceiptAllocation).where(
                    CustomerReceiptAllocation.receipt_id == receipt_id
                )
            )
        ).scalars().all()
        receipt = await service.get_customer_receipt(db_session, ar_setup.tenant_id, receipt_id)
        lines = (
            await db_session.execute(
                select(JournalLine).where(JournalLine.journal_entry_id == receipt.journal_entry_id)
            )
        ).scalars().all()
    assert len(allocations) == 1
    assert Decimal(str(allocations[0].allocated_amount)) == Decimal("100.00")
    # Cr AR / Dr bank, balanced.
    debit = sum((Decimal(str(line.functional_debit_amount)) for line in lines), Decimal(0))
    credit = sum((Decimal(str(line.functional_credit_amount)) for line in lines), Decimal(0))
    assert debit == credit == Decimal("100.00")
    ar_line = next(line for line in lines if line.account_id == ar_setup.accounts["1200"])
    bank_line = next(line for line in lines if line.account_id == ar_setup.accounts["1000"])
    assert Decimal(str(ar_line.transaction_credit_amount)) == Decimal("100.00")
    assert Decimal(str(bank_line.transaction_debit_amount)) == Decimal("100.00")


async def test_partial_receipt_reduces_open_amount(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    invoice = await _create_and_post_invoice(db_session, ar_setup, _invoice_payload(ar_setup))
    await _receive_invoice(db_session, ar_setup, invoice, "40.00")
    assert invoice.status == InvoiceStatus.PARTIALLY_PAID.value
    assert Decimal(str(invoice.open_amount)) == Decimal("60.00")


async def test_cannot_receipt_a_draft_invoice(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    with tenant_context(ar_setup.tenant_id):
        invoice = await service.create_customer_invoice(
            db_session, ar_setup.tenant_id, _invoice_payload(ar_setup)
        )
        await db_session.commit()
        with pytest.raises(ConflictError) as exc:
            await service.create_and_post_receipt(
                db_session,
                ar_setup.tenant_id,
                CustomerReceiptCreate(
                    partner_id=invoice.partner_id,
                    partner_name=invoice.partner_name,
                    receipt_date=_RECEIPT_DATE,
                    currency_code="USD",
                    bank_account_id=ar_setup.accounts["1000"],
                    amount=Decimal("100.00"),
                    allocations=[
                        ReceiptAllocationCreate(invoice_id=invoice.id, amount=Decimal("100.00"))
                    ],
                ),
            )
    assert exc.value.code == "finance.invoice_not_open"


async def test_cannot_receipt_a_paid_invoice(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    invoice = await _create_and_post_invoice(db_session, ar_setup, _invoice_payload(ar_setup))
    await _receive_invoice(db_session, ar_setup, invoice, "100.00")  # now PAID
    with tenant_context(ar_setup.tenant_id), pytest.raises(ConflictError) as exc:
        await service.create_and_post_receipt(
            db_session,
            ar_setup.tenant_id,
            CustomerReceiptCreate(
                partner_id=invoice.partner_id,
                partner_name=invoice.partner_name,
                receipt_date=_RECEIPT_DATE,
                currency_code="USD",
                bank_account_id=ar_setup.accounts["1000"],
                amount=Decimal("10.00"),
                allocations=[
                    ReceiptAllocationCreate(invoice_id=invoice.id, amount=Decimal("10.00"))
                ],
            ),
        )
    assert exc.value.code == "finance.invoice_not_open"


async def test_cannot_overreceive_an_invoice(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    invoice = await _create_and_post_invoice(db_session, ar_setup, _invoice_payload(ar_setup))
    with tenant_context(ar_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_and_post_receipt(
            db_session,
            ar_setup.tenant_id,
            CustomerReceiptCreate(
                partner_id=invoice.partner_id,
                partner_name=invoice.partner_name,
                receipt_date=_RECEIPT_DATE,
                currency_code="USD",
                bank_account_id=ar_setup.accounts["1000"],
                amount=Decimal("150.00"),
                allocations=[
                    ReceiptAllocationCreate(invoice_id=invoice.id, amount=Decimal("150.00"))
                ],
            ),
        )
    assert exc.value.code == "finance.receipt_overallocated"


async def test_an_overpayment_lands_unapplied_and_never_in_a_phantom_fx_line(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    """Regression for #73, restated for PLAN 20.4 (D-084). #73 was never "over-payment is illegal"
    — it was "the difference must not be misbooked as a realized FX gain". The widening keeps that
    invariant and gives the difference a real home: 110 received against a 100 invoice clears the
    invoice, credits 10 to the advance control, and posts NO FX line in a single-currency tenant.

    A tenant that never mapped ``customer_advances`` gets a loud 422 instead of a guessed account —
    asserted first, because that is what every existing AR tenant sees the day this ships."""
    invoice = await _create_and_post_invoice(db_session, ar_setup, _invoice_payload(ar_setup))
    payload = CustomerReceiptCreate(
        partner_id=invoice.partner_id,
        partner_name=invoice.partner_name,
        receipt_date=_RECEIPT_DATE,
        currency_code="USD",
        bank_account_id=ar_setup.accounts["1000"],
        amount=Decimal("110.00"),
        allocations=[ReceiptAllocationCreate(invoice_id=invoice.id, amount=Decimal("100.00"))],
    )
    with tenant_context(ar_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_and_post_receipt(db_session, ar_setup.tenant_id, payload)
    assert exc.value.code == "finance.posting_default_unmapped"

    advance_id = await seed_advance_account(db_session, ar_setup.tenant_id)
    holder: dict[str, uuid.UUID] = {}
    with tenant_context(ar_setup.tenant_id):

        async def work() -> None:
            receipt = await service.create_and_post_receipt(
                db_session, ar_setup.tenant_id, payload
            )
            holder["receipt_id"] = receipt.id

        await run_in_uow(db_session, work)
        await db_session.refresh(invoice)
        receipt = await service.get_customer_receipt(
            db_session, ar_setup.tenant_id, holder["receipt_id"]
        )
        lines = (
            await db_session.execute(
                select(JournalLine).where(JournalLine.journal_entry_id == receipt.journal_entry_id)
            )
        ).scalars().all()

    assert invoice.status == InvoiceStatus.PAID.value
    assert Decimal(str(receipt.unapplied_amount)) == Decimal("10.00")
    # Three lines exactly: Dr bank 110, Cr AR 100, Cr advance 10. A fourth would BE the #73 bug.
    assert len(lines) == 3
    advance_line = next(line for line in lines if line.account_id == advance_id)
    assert Decimal(str(advance_line.transaction_credit_amount)) == Decimal("10.00")


# --- dunning ------------------------------------------------------------------


async def _run_dunning(
    session: AsyncSession, setup: ArSetup, as_of: date
) -> dict[str, object]:
    with tenant_context(setup.tenant_id):
        holder: dict[str, dict[str, object]] = {}

        async def work() -> None:
            holder["run"] = await service.run_dunning(session, setup.tenant_id, as_of)

        await run_in_uow(session, work)
        return holder["run"]


async def test_dunning_advances_level_1_past_threshold(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    # Due 2026-03-31; as_of 2026-04-10 -> 10 days overdue -> earns level 1 (threshold 7).
    invoice = await _create_and_post_invoice(db_session, ar_setup, _invoice_payload(ar_setup))
    run = await _run_dunning(db_session, ar_setup, date(2026, 4, 10))
    await db_session.refresh(invoice)
    assert invoice.dunning_level == 1
    assert invoice.last_dunned_date == date(2026, 4, 10)
    notices = run["notices"]
    assert len(notices) == 1
    assert notices[0]["invoice_id"] == invoice.id
    assert notices[0]["previous_level"] == 0
    assert notices[0]["new_level"] == 1


async def test_dunning_jumps_to_level_3_when_far_overdue(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    # Due 2026-03-31; as_of 2026-06-10 -> 71 days overdue -> earns level 3 (thresholds 7/30/60).
    invoice = await _create_and_post_invoice(db_session, ar_setup, _invoice_payload(ar_setup))
    await _run_dunning(db_session, ar_setup, date(2026, 6, 10))
    await db_session.refresh(invoice)
    assert invoice.dunning_level == 3


async def test_dunning_does_not_touch_current_invoice(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    # Due 2026-06-30; as_of 2026-04-10 -> not yet due -> excluded, stays level 0.
    invoice = await _create_and_post_invoice(
        db_session, ar_setup, _invoice_payload(ar_setup, due_date=date(2026, 6, 30))
    )
    run = await _run_dunning(db_session, ar_setup, date(2026, 4, 10))
    await db_session.refresh(invoice)
    assert invoice.dunning_level == 0
    assert invoice.last_dunned_date is None
    assert run["notices"] == []


async def test_dunning_rerun_same_day_does_not_advance(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    invoice = await _create_and_post_invoice(db_session, ar_setup, _invoice_payload(ar_setup))
    first = await _run_dunning(db_session, ar_setup, date(2026, 4, 10))
    assert len(first["notices"]) == 1
    # Re-running the SAME as_of advances nothing (already at the earned level).
    second = await _run_dunning(db_session, ar_setup, date(2026, 4, 10))
    await db_session.refresh(invoice)
    assert second["notices"] == []
    assert invoice.dunning_level == 1


async def test_dunning_advances_step_by_step_over_time(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    invoice = await _create_and_post_invoice(db_session, ar_setup, _invoice_payload(ar_setup))
    await _run_dunning(db_session, ar_setup, date(2026, 4, 10))  # 10 days -> level 1
    await db_session.refresh(invoice)
    assert invoice.dunning_level == 1
    # 2026-05-05 -> 35 days overdue -> level 2 (threshold 30).
    run = await _run_dunning(db_session, ar_setup, date(2026, 5, 5))
    await db_session.refresh(invoice)
    assert invoice.dunning_level == 2
    assert run["notices"][0]["previous_level"] == 1
    assert run["notices"][0]["new_level"] == 2


# --- aging --------------------------------------------------------------------


async def test_aging_buckets_by_days_overdue(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    # Three invoices due on different dates; aging as of 2026-04-15.
    await _create_and_post_invoice(
        db_session, ar_setup, _invoice_payload(ar_setup, net="10.00", due_date=date(2026, 4, 30))
    )  # not yet due -> current
    await _create_and_post_invoice(
        db_session, ar_setup, _invoice_payload(ar_setup, net="20.00", due_date=date(2026, 4, 1))
    )  # 14 days overdue -> 1-30
    await _create_and_post_invoice(
        db_session, ar_setup, _invoice_payload(ar_setup, net="30.00", due_date=date(2026, 3, 1))
    )  # 45 days overdue -> 31-60
    with tenant_context(ar_setup.tenant_id):
        report = await service.customer_aging(db_session, ar_setup.tenant_id, date(2026, 4, 15))
    assert report["current"] == Decimal("10.00")
    assert report["days_1_30"] == Decimal("20.00")
    assert report["days_31_60"] == Decimal("30.00")
    assert report["total"] == Decimal("60.00")


# --- queries ------------------------------------------------------------------


async def test_open_customer_invoices_query(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    partner = uuid.uuid4()
    invoice = await _create_and_post_invoice(
        db_session, ar_setup, _invoice_payload(ar_setup, partner_id=partner)
    )
    with tenant_context(ar_setup.tenant_id):
        open_invoices = await queries.get_open_customer_invoices(
            db_session, ar_setup.tenant_id, partner
        )
    assert [i.id for i in open_invoices] == [invoice.id]


async def test_customer_open_balance_sums_open_invoices(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    partner = uuid.uuid4()
    # Two open invoices (70 + 30) + one fully received (so excluded).
    await _create_and_post_invoice(
        db_session, ar_setup, _invoice_payload(ar_setup, net="70.00", partner_id=partner)
    )
    await _create_and_post_invoice(
        db_session, ar_setup, _invoice_payload(ar_setup, net="30.00", partner_id=partner)
    )
    paid = await _create_and_post_invoice(
        db_session, ar_setup, _invoice_payload(ar_setup, net="50.00", partner_id=partner)
    )
    await _receive_invoice(db_session, ar_setup, paid, "50.00")
    with tenant_context(ar_setup.tenant_id):
        balance = await queries.customer_open_balance(db_session, ar_setup.tenant_id, partner)
    assert balance == Decimal("100.00")
    # A partner with no open invoices reads 0.
    with tenant_context(ar_setup.tenant_id):
        empty = await queries.customer_open_balance(db_session, ar_setup.tenant_id, uuid.uuid4())
    assert empty == Decimal(0)


# --- idempotency --------------------------------------------------------------


async def test_post_invoice_is_idempotent(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    with tenant_context(ar_setup.tenant_id):
        invoice = await service.create_customer_invoice(
            db_session, ar_setup.tenant_id, _invoice_payload(ar_setup)
        )
        await db_session.commit()

        async def work() -> None:
            await service.post_customer_invoice(db_session, ar_setup.tenant_id, invoice.id)

        await run_in_uow(db_session, work)
        await db_session.refresh(invoice)
        first_number = invoice.invoice_number
        # A second post returns the same invoice unchanged (no second number).
        await service.post_customer_invoice(db_session, ar_setup.tenant_id, invoice.id)
        await db_session.refresh(invoice)
    assert invoice.invoice_number == first_number
    assert invoice.status == InvoiceStatus.POSTED.value


async def test_receipt_status_is_posted(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    invoice = await _create_and_post_invoice(db_session, ar_setup, _invoice_payload(ar_setup))
    receipt_id = await _receive_invoice(db_session, ar_setup, invoice, "100.00")
    with tenant_context(ar_setup.tenant_id):
        receipt = await service.get_customer_receipt(db_session, ar_setup.tenant_id, receipt_id)
    assert receipt.status == ReceiptStatus.POSTED.value
    assert receipt.receipt_number == "RCT-2026-00001"


# --- tenant isolation ---------------------------------------------------------


async def test_invoice_is_tenant_isolated(
    db_session: AsyncSession, ar_setup: ArSetup, tenant_b: uuid.UUID
) -> None:
    invoice = await _create_and_post_invoice(db_session, ar_setup, _invoice_payload(ar_setup))
    from app.core.exceptions import NotFoundError

    with tenant_context(tenant_b), pytest.raises(NotFoundError):
        await service.get_customer_invoice(db_session, tenant_b, invoice.id)
