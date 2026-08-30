"""Named pins for EVERY rule ``create_and_post_receipt`` enforces today (Phase 20 Task 1).

Phase 20 Task 2 (PLAN 20.4) widens ``CustomerReceipt`` into an unapplied/on-account receipt so a
hospitality advance deposit has a home in finance. That rewrites the validation spine of a SHIPPED,
seeded, order-to-cash-driven path, so every rule the spine enforces gets a named test HERE, BEFORE
the change — a rule nobody named is a rule the widening can move silently.

Each docstring states the handoff: RELAXED means Task 2 changes the rule and must update the pin in
the SAME commit (never delete it); KEPT means the rule survives the widening unchanged and a pin
turning red is a bug in Task 2, not a stale test.

The rules pinned (``service/customer_receipts.py``, in the order the service checks them):
  1. finance.ar_bank_account_not_found        KEPT (and checked FIRST, before any allocation)
  2. finance.receipt_no_allocations           RELAXED
  3. finance.customer_invoice_not_found       KEPT (incl. D-007: another tenant's invoice)
  4. finance.invoice_not_open                 KEPT (ConflictError, 409)
  5. finance.receipt_partner_mismatch         KEPT
  6. finance.receipt_currency_mismatch        KEPT
  7. finance.receipt_allocation_not_positive  KEPT
  8. finance.receipt_overallocated            KEPT
  9. finance.receipt_allocation_sum_mismatch  RELAXED (== becomes >=; over-allocation still refused)
 10. the posted shape of a fully allocated receipt (journal, allocation row, invoice flip, gapless
     number, docflow links, event)            KEPT

Invoice helpers are imported from test_receivables.py rather than rebuilt (the
test_bank_reconcile.py precedent) so both suites post the same invoice.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.events import run_in_uow, subscribe
from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.finance import service
from app.modules.finance.constants import InvoiceStatus, ReceiptStatus
from app.modules.finance.events import CustomerReceiptPosted
from app.modules.finance.models import CustomerReceiptAllocation, JournalLine
from app.modules.finance.receivables_schemas import (
    CustomerReceiptCreate,
    ReceiptAllocationCreate,
)
from tests.modules.finance.conftest import ArSetup
from tests.modules.finance.factories import build_ar_setup
from tests.modules.finance.test_receivables import (
    _RECEIPT_DATE,
    _create_and_post_invoice,
    _invoice_payload,
)


def _alloc(invoice_id: uuid.UUID, amount: str) -> ReceiptAllocationCreate:
    return ReceiptAllocationCreate(invoice_id=invoice_id, amount=Decimal(amount))


def _receipt(
    setup: ArSetup,
    *,
    partner_id: uuid.UUID,
    amount: str,
    allocations: list[ReceiptAllocationCreate],
    currency_code: str = "USD",
    bank_account_id: uuid.UUID | None = None,
) -> CustomerReceiptCreate:
    return CustomerReceiptCreate(
        partner_id=partner_id,
        partner_name="Globex Inc",
        receipt_date=_RECEIPT_DATE,
        currency_code=currency_code,
        bank_account_id=setup.accounts["1000"] if bank_account_id is None else bank_account_id,
        amount=Decimal(amount),
        allocations=allocations,
    )


async def _refused(
    session: AsyncSession,
    setup: ArSetup,
    payload: CustomerReceiptCreate,
    error: type[Exception],
) -> str:
    """Post the receipt expecting ``error``; return its code so each pin asserts the EXACT code."""
    with tenant_context(setup.tenant_id), pytest.raises(error) as exc:
        await service.create_and_post_receipt(session, setup.tenant_id, payload)
    return exc.value.code


async def test_the_bank_account_must_exist_in_this_tenant_and_is_checked_first(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    """Pins finance.ar_bank_account_not_found (customer_receipts.py's first statement, via
    clearing_fx.require_bank_account). Task 2 must KEEP it — an unapplied receipt still debits a
    real bank account — and must keep it FIRST: the payload below is invalid twice over (unknown
    bank AND no allocations) and today's answer is the bank, which stays true once the
    no-allocations rule is relaxed."""
    code = await _refused(
        db_session,
        ar_setup,
        _receipt(
            ar_setup,
            partner_id=uuid.uuid4(),
            amount="100.00",
            allocations=[],
            bank_account_id=uuid.uuid4(),
        ),
        ValidationFailedError,
    )
    assert code == "finance.ar_bank_account_not_found"


async def test_a_receipt_with_no_allocations_is_refused_today(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    """Pins finance.receipt_no_allocations (customer_receipts.py:66-70). Task 2 RELAXES this rule
    deliberately — when it does, this test is UPDATED IN THE SAME COMMIT to assert the new
    contract (unapplied receipt accepted, unapplied_amount == amount), never deleted."""
    code = await _refused(
        db_session,
        ar_setup,
        _receipt(ar_setup, partner_id=uuid.uuid4(), amount="100.00", allocations=[]),
        ValidationFailedError,
    )
    assert code == "finance.receipt_no_allocations"


async def test_an_allocation_must_reference_an_invoice_of_this_tenant(
    db_session: AsyncSession, ar_setup: ArSetup, tenant_b: uuid.UUID
) -> None:
    """Pins finance.customer_invoice_not_found (customer_receipts.py:72-78), both halves: an id
    that exists nowhere, and D-007 — another tenant's real invoice is 'not found', never clearable
    across the tenant boundary. Task 2 must NOT relax either half."""
    unknown = await _refused(
        db_session,
        ar_setup,
        _receipt(
            ar_setup,
            partner_id=uuid.uuid4(),
            amount="100.00",
            allocations=[_alloc(uuid.uuid4(), "100.00")],
        ),
        ValidationFailedError,
    )
    assert unknown == "finance.customer_invoice_not_found"

    other_setup = await build_ar_setup(db_session, tenant_b)
    other_invoice = await _create_and_post_invoice(
        db_session, other_setup, _invoice_payload(other_setup)
    )
    cross_tenant = await _refused(
        db_session,
        ar_setup,
        _receipt(
            ar_setup,
            partner_id=other_invoice.partner_id,
            amount="100.00",
            allocations=[_alloc(other_invoice.id, "100.00")],
        ),
        ValidationFailedError,
    )
    assert cross_tenant == "finance.customer_invoice_not_found"


async def test_an_allocation_must_reference_a_posted_open_invoice(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    """Pins finance.invoice_not_open (customer_receipts.py:79-88) — a 409, not a 422: only a
    POSTED or PARTIALLY_PAID invoice can be cleared, so a DRAFT one is refused. Task 2 must NOT
    relax this — an applied allocation keeps every existing rule."""
    with tenant_context(ar_setup.tenant_id):
        invoice = await service.create_customer_invoice(
            db_session, ar_setup.tenant_id, _invoice_payload(ar_setup)
        )
        await db_session.commit()
    assert invoice.status == InvoiceStatus.DRAFT.value
    code = await _refused(
        db_session,
        ar_setup,
        _receipt(
            ar_setup,
            partner_id=invoice.partner_id,
            amount="100.00",
            allocations=[_alloc(invoice.id, "100.00")],
        ),
        ConflictError,
    )
    assert code == "finance.invoice_not_open"


async def test_allocations_must_reference_posted_invoices_of_the_same_partner(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    """Pins customer_receipts.py:72-90. Task 2 must NOT relax this — an applied allocation keeps
    every existing rule."""
    invoice = await _create_and_post_invoice(db_session, ar_setup, _invoice_payload(ar_setup))
    code = await _refused(
        db_session,
        ar_setup,
        _receipt(
            ar_setup,
            partner_id=uuid.uuid4(),
            amount="100.00",
            allocations=[_alloc(invoice.id, "100.00")],
        ),
        ValidationFailedError,
    )
    assert code == "finance.receipt_partner_mismatch"


async def test_allocations_must_share_the_receipt_currency(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    """Pins finance.receipt_currency_mismatch (customer_receipts.py:91-97): the D-019 clearing math
    freezes each invoice's functional rate, so a receipt cannot clear an invoice denominated in
    another currency. Task 2 must NOT relax this — cross-currency stays refused for applied
    allocations AND for apply_receipt."""
    invoice = await _create_and_post_invoice(db_session, ar_setup, _invoice_payload(ar_setup))
    code = await _refused(
        db_session,
        ar_setup,
        _receipt(
            ar_setup,
            partner_id=invoice.partner_id,
            amount="100.00",
            allocations=[_alloc(invoice.id, "100.00")],
            currency_code="EUR",
        ),
        ValidationFailedError,
    )
    assert code == "finance.receipt_currency_mismatch"


async def test_an_allocation_amount_must_be_positive(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    """Pins finance.receipt_allocation_not_positive (customer_receipts.py:98-104) — the check runs
    on the QUANTIZED amount, so a sub-cent allocation is 'not positive', not a silent zero-value
    clearing row. Task 2 must NOT relax this: an unapplied receipt carries no allocation at all
    rather than a zero one."""
    invoice = await _create_and_post_invoice(db_session, ar_setup, _invoice_payload(ar_setup))
    for amount in ("-5.00", "0.001"):
        code = await _refused(
            db_session,
            ar_setup,
            _receipt(
                ar_setup,
                partner_id=invoice.partner_id,
                amount=amount,
                allocations=[_alloc(invoice.id, amount)],
            ),
            ValidationFailedError,
        )
        assert code == "finance.receipt_allocation_not_positive"


async def test_an_allocation_cannot_exceed_the_invoices_open_amount(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    """Pins finance.receipt_overallocated (customer_receipts.py:105-111). Task 2 must NOT relax
    this — the excess cash becomes unapplied_amount, it never over-clears an invoice."""
    invoice = await _create_and_post_invoice(db_session, ar_setup, _invoice_payload(ar_setup))
    code = await _refused(
        db_session,
        ar_setup,
        _receipt(
            ar_setup,
            partner_id=invoice.partner_id,
            amount="150.00",
            allocations=[_alloc(invoice.id, "150.00")],
        ),
        ValidationFailedError,
    )
    assert code == "finance.receipt_overallocated"


async def test_receipt_amount_must_equal_allocation_sum_today(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    """Pins customer_receipts.py:186-190. Task 2 changes '==' to '>=' (the excess becomes
    unapplied); the updated pin asserts over-allocation is still refused.

    Both directions are pinned because they part company under the widening: amount ABOVE the
    allocation sum becomes legal (the shortfall lands unapplied) while amount BELOW it stays
    refused — allocating cash the receipt never received is the #73 phantom-FX bug with the sign
    flipped."""
    invoice = await _create_and_post_invoice(db_session, ar_setup, _invoice_payload(ar_setup))
    over = await _refused(
        db_session,
        ar_setup,
        _receipt(
            ar_setup,
            partner_id=invoice.partner_id,
            amount="110.00",
            allocations=[_alloc(invoice.id, "100.00")],
        ),
        ValidationFailedError,
    )
    assert over == "finance.receipt_allocation_sum_mismatch"
    under = await _refused(
        db_session,
        ar_setup,
        _receipt(
            ar_setup,
            partner_id=invoice.partner_id,
            amount="40.00",
            allocations=[_alloc(invoice.id, "60.00")],
        ),
        ValidationFailedError,
    )
    assert under == "finance.receipt_allocation_sum_mismatch"


async def test_a_fully_allocated_receipt_keeps_its_whole_posted_shape(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    """The positive half of the net: everything a POSTED, fully allocated receipt is today, in one
    assertion block — balanced Cr AR / Dr bank journal, the allocation row, the invoice flipped to
    PAID with a zero open amount, the gapless receipt number, BOTH docflow links (the 'posts' link
    to its clearing journal and the 'receipts' link to the invoice) and the CustomerReceiptPosted
    event carrying the cleared ids.

    Task 2 must KEEP every line of this. The widening's whole safety claim is that the allocated
    path is untouched, and the docflow/event/numbering half of that claim is asserted nowhere else
    — test_receivables.py pins the money, not the wiring."""
    invoice = await _create_and_post_invoice(db_session, ar_setup, _invoice_payload(ar_setup))
    captured: list[CustomerReceiptPosted] = []

    async def _capture(_s: AsyncSession, event: CustomerReceiptPosted) -> None:
        captured.append(event)

    subscribe(CustomerReceiptPosted.key, _capture)
    holder: dict[str, uuid.UUID] = {}
    with tenant_context(ar_setup.tenant_id):

        async def work() -> None:
            receipt = await service.create_and_post_receipt(
                db_session,
                ar_setup.tenant_id,
                _receipt(
                    ar_setup,
                    partner_id=invoice.partner_id,
                    amount="100.00",
                    allocations=[_alloc(invoice.id, "100.00")],
                ),
            )
            holder["receipt_id"] = receipt.id

        await run_in_uow(db_session, work)
        await db_session.refresh(invoice)

        receipt = await service.get_customer_receipt(
            db_session, ar_setup.tenant_id, holder["receipt_id"]
        )
        allocations = (
            await db_session.execute(
                select(CustomerReceiptAllocation).where(
                    CustomerReceiptAllocation.receipt_id == receipt.id
                )
            )
        ).scalars().all()
        lines = (
            await db_session.execute(
                select(JournalLine).where(JournalLine.journal_entry_id == receipt.journal_entry_id)
            )
        ).scalars().all()
        chain = await docflow.get_document_chain(
            db_session, ar_setup.tenant_id, receipt.document_id
        )

    assert receipt.status == ReceiptStatus.POSTED.value
    assert receipt.receipt_number == "RCT-2026-00001"
    assert Decimal(str(receipt.amount)) == Decimal("100.00")
    assert invoice.status == InvoiceStatus.PAID.value
    assert Decimal(str(invoice.open_amount)) == Decimal("0.00")
    assert len(allocations) == 1
    assert Decimal(str(allocations[0].allocated_amount)) == Decimal("100.00")

    debit = sum((Decimal(str(line.functional_debit_amount)) for line in lines), Decimal(0))
    credit = sum((Decimal(str(line.functional_credit_amount)) for line in lines), Decimal(0))
    assert debit == credit == Decimal("100.00")
    ar_line = next(line for line in lines if line.account_id == ar_setup.accounts["1200"])
    bank_line = next(line for line in lines if line.account_id == ar_setup.accounts["1000"])
    assert Decimal(str(ar_line.transaction_credit_amount)) == Decimal("100.00")
    assert Decimal(str(bank_line.transaction_debit_amount)) == Decimal("100.00")

    outgoing = {
        edge.link_type
        for edge in chain.edges
        if edge.predecessor_document_id == receipt.document_id
    }
    assert outgoing == {"posts", "receipts"}

    assert len(captured) == 1
    assert captured[0].receipt_id == receipt.id
    assert captured[0].amount == Decimal("100.00")
    assert captured[0].cleared_invoice_ids == (invoice.id,)
