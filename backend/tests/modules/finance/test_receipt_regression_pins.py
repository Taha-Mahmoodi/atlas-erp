"""Named pins for EVERY rule ``create_and_post_receipt`` enforces today (Phase 20 Task 1).

Phase 20 Task 2 (PLAN 20.4) widens ``CustomerReceipt`` into an unapplied/on-account receipt so a
hospitality advance deposit has a home in finance. That rewrites the validation spine of a SHIPPED,
seeded, order-to-cash-driven path, so every rule the spine enforces gets a named test HERE, BEFORE
the change — a rule nobody named is a rule the widening can move silently.

Each docstring states the handoff: RELAXED means Task 2 changes the rule and must update the pin in
the SAME commit (never delete it); KEPT means the rule survives the widening unchanged and a pin
turning red is a bug in Task 2, not a stale test. Task 2 has landed: the two RELAXED pins below now
assert the NEW contract, and the nine KEPT ones are unchanged from the day they were written.

The rules pinned (``service/customer_receipts.py``, in the order the service checks them):
  1. finance.ar_bank_account_not_found        KEPT (and checked FIRST, before any allocation)
  2. finance.receipt_no_allocations           RELAXED -> an allocationless receipt is unapplied
  3. finance.customer_invoice_not_found       KEPT (incl. D-007: another tenant's invoice)
  4. finance.invoice_not_open                 KEPT (ConflictError, 409)
  5. finance.receipt_partner_mismatch         KEPT
  6. finance.receipt_currency_mismatch        KEPT
  7. finance.receipt_allocation_not_positive  KEPT
  8. finance.receipt_overallocated            KEPT
  9. finance.receipt_allocation_sum_mismatch  RELAXED (== became >=; under-payment still refused)
 10. the posted shape of a fully allocated receipt (journal, allocation row, invoice flip, gapless
     number, docflow links, event)            KEPT
 11. the same shape PER INVOICE when one receipt clears TWO (one allocation row and one 'receipts'
     link each, both ids on the event)        KEPT — the shape Task 2's `amount == sum` -> `>=`
                                              split actually operates on, and the one shape no
                                              test in this repo posted before

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
from tests.modules.finance.factories import build_ar_setup, seed_advance_account
from tests.modules.finance.test_receivables import (
    _RECEIPT_DATE,
    _create_and_post_invoice,
    _invoice_payload,
    _receive_invoice,
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


async def test_a_receipt_with_no_allocations_is_now_an_unapplied_receipt(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    """WAS: finance.receipt_no_allocations refused an allocationless receipt. Task 2 RELAXED that
    rule deliberately (PLAN 20.4, D-084) and this pin is updated in the same commit, not deleted:
    the receipt is now ACCEPTED and its whole amount stands as ``unapplied_amount``, on-account
    money awaiting an invoice. What the rule cost — a receipt that clears nothing and posts
    nowhere — is now bought by the advance control account instead.

    The full behaviour of that path (the advance line, its partner stamp, apply, the partner
    ledger) lives in test_unapplied_receipts.py; this pin only holds the door open."""
    partner_id = uuid.uuid4()
    await seed_advance_account(db_session, ar_setup.tenant_id)
    with tenant_context(ar_setup.tenant_id):

        async def work() -> None:
            receipt = await service.create_and_post_receipt(
                db_session,
                ar_setup.tenant_id,
                _receipt(ar_setup, partner_id=partner_id, amount="100.00", allocations=[]),
            )
            holder["receipt_id"] = receipt.id

        holder: dict[str, uuid.UUID] = {}
        await run_in_uow(db_session, work)
        receipt = await service.get_customer_receipt(
            db_session, ar_setup.tenant_id, holder["receipt_id"]
        )

    assert receipt.status == ReceiptStatus.POSTED.value
    assert Decimal(str(receipt.unapplied_amount)) == Decimal("100.00")
    assert Decimal(str(receipt.amount)) == Decimal("100.00")


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
    this — the excess cash becomes unapplied_amount, it never over-clears an invoice.

    The SECOND half is the one that pins the boundary. On a FRESH invoice ``open == gross``, so a
    pin that only over-receives a fresh invoice passes just as well against a guard reading
    ``invoice.gross_amount`` — the whole finance suite does, which is why this shape existed
    nowhere. A PARTIALLY_PAID invoice separates the two: 100 billed, 40 received, 80 attempted is
    under gross and over open, and it is exactly the boundary Task 2's "the excess becomes
    unapplied_amount, it never over-clears" logic straddles."""
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

    await _receive_invoice(db_session, ar_setup, invoice, "40.00")
    assert invoice.status == InvoiceStatus.PARTIALLY_PAID.value
    assert Decimal(str(invoice.open_amount)) == Decimal("60.00")
    partial = await _refused(
        db_session,
        ar_setup,
        _receipt(
            ar_setup,
            partner_id=invoice.partner_id,
            amount="80.00",
            allocations=[_alloc(invoice.id, "80.00")],
        ),
        ValidationFailedError,
    )
    assert partial == "finance.receipt_overallocated"


async def test_a_receipt_above_its_allocation_sum_is_unapplied_and_below_it_is_refused(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    """WAS: ``amount == sum(allocations)`` in BOTH directions. Task 2 changed it to ``>=``, and the
    two halves part company exactly as this pin predicted — so the pin is updated, not deleted:

    * amount ABOVE the sum is now LEGAL: 110 received against a 100 invoice clears the invoice and
      leaves 10 unapplied (the over-payment a hotel guest makes at check-out, and the same
      mechanism as a deposit).
    * amount BELOW the sum stays REFUSED with the same finance.receipt_allocation_sum_mismatch —
      allocating cash the receipt never received is #73 with the sign flipped, and the difference
      would flow into the realized-FX line as a phantom gain."""
    await seed_advance_account(db_session, ar_setup.tenant_id)
    invoice = await _create_and_post_invoice(db_session, ar_setup, _invoice_payload(ar_setup))
    holder: dict[str, uuid.UUID] = {}
    with tenant_context(ar_setup.tenant_id):

        async def work() -> None:
            receipt = await service.create_and_post_receipt(
                db_session,
                ar_setup.tenant_id,
                _receipt(
                    ar_setup,
                    partner_id=invoice.partner_id,
                    amount="110.00",
                    allocations=[_alloc(invoice.id, "100.00")],
                ),
            )
            holder["receipt_id"] = receipt.id

        await run_in_uow(db_session, work)
        await db_session.refresh(invoice)
        over = await service.get_customer_receipt(
            db_session, ar_setup.tenant_id, holder["receipt_id"]
        )

    assert invoice.status == InvoiceStatus.PAID.value
    assert Decimal(str(over.amount)) == Decimal("110.00")
    assert Decimal(str(over.unapplied_amount)) == Decimal("10.00")

    # A second, still-open invoice: the first one is PAID now, and an under-payment of a PAID
    # invoice would be refused for the WRONG reason (finance.invoice_not_open, 409).
    still_open = await _create_and_post_invoice(db_session, ar_setup, _invoice_payload(ar_setup))
    under = await _refused(
        db_session,
        ar_setup,
        _receipt(
            ar_setup,
            partner_id=still_open.partner_id,
            amount="40.00",
            allocations=[_alloc(still_open.id, "60.00")],
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

    # COUNTED, not set-compared, for the same reason the two-invoice pin counts: a set of link
    # types cannot see HOW MANY of each there are. With one invoice a duplicate link is impossible
    # anyway (the docflow unique constraint refuses it), so this is consistency here; the counting
    # bite is in test_a_receipt_clearing_two_invoices_writes_one_row_and_one_link_per_invoice.
    outgoing = [
        edge.link_type
        for edge in chain.edges
        if edge.predecessor_document_id == receipt.document_id
    ]
    assert sorted(outgoing) == ["posts", "receipts"]

    assert len(captured) == 1
    assert captured[0].receipt_id == receipt.id
    assert captured[0].amount == Decimal("100.00")
    assert captured[0].cleared_invoice_ids == (invoice.id,)


async def test_a_receipt_clearing_two_invoices_writes_one_row_and_one_link_per_invoice(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    """The multi-allocation shape — the one NO test in this repo posted before, and the one Task
    2's `amount == sum(allocations)` -> `amount >= sum(allocations)` split actually operates on.

    Single-allocation pins cannot see the per-invoice half of the contract: with one allocation,
    ``allocated_amount=amount`` and ``allocated_amount=receipt_amount`` are the same number, and
    linking ``pairs[0][0]`` is the same as linking every pair. Two invoices of DIFFERENT amounts
    separate them, so this pins, per cleared invoice: its own allocation row carrying ITS OWN
    amount, its own ``receipts`` docflow edge (COUNTED — a set of link types cannot count), and its
    id on ``CustomerReceiptPosted.cleared_invoice_ids``.

    Task 2 must KEEP all three. An unapplied receipt adds a residual on TOP of these rows; it must
    not fold them into one aggregate allocation or one representative link."""
    partner_id = uuid.uuid4()
    first = await _create_and_post_invoice(
        db_session, ar_setup, _invoice_payload(ar_setup, net="100.00", partner_id=partner_id)
    )
    second = await _create_and_post_invoice(
        db_session, ar_setup, _invoice_payload(ar_setup, net="50.00", partner_id=partner_id)
    )
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
                    partner_id=partner_id,
                    amount="150.00",
                    allocations=[_alloc(first.id, "100.00"), _alloc(second.id, "50.00")],
                ),
            )
            holder["receipt_id"] = receipt.id

        await run_in_uow(db_session, work)
        await db_session.refresh(first)
        await db_session.refresh(second)

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
        chain = await docflow.get_document_chain(
            db_session, ar_setup.tenant_id, receipt.document_id
        )

    assert first.status == second.status == InvoiceStatus.PAID.value

    # ONE allocation row per invoice, each carrying ITS OWN amount — not the receipt's total and
    # not one aggregate row.
    by_invoice = {
        allocation.customer_invoice_id: Decimal(str(allocation.allocated_amount))
        for allocation in allocations
    }
    assert len(allocations) == 2
    assert by_invoice == {first.id: Decimal("100.00"), second.id: Decimal("50.00")}

    # ONE 'receipts' edge per cleared invoice, COUNTED per successor: a set of link types is blind
    # to a rewrite that links only the first pair.
    receipts_edges = [
        edge.successor_document_id
        for edge in chain.edges
        if edge.predecessor_document_id == receipt.document_id
        and edge.link_type == "receipts"
    ]
    assert sorted(receipts_edges, key=str) == sorted(
        [first.document_id, second.document_id], key=str
    )

    assert len(captured) == 1
    assert set(captured[0].cleared_invoice_ids) == {first.id, second.id}
