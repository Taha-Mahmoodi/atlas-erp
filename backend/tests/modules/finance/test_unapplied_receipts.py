"""Unapplied / on-account customer receipts (PLAN 20.4, D-084).

A hospitality advance deposit is cash received BEFORE any invoice exists, so it has no allocation
to make. Phase 20 Task 2 widens ``CustomerReceipt`` rather than giving hospitality its own deposit
table (two clearing engines rot): the shortfall between the receipt ``amount`` and the sum of its
allocations lands in ``unapplied_amount`` and credits the ``customer_advances`` posting-default
account with ``partner_type``/``partner_id`` stamped, and ``apply_receipt`` later reclasses that
credit onto a real invoice through the SAME ``clearing_fx`` path a direct allocation uses.

Every rule the allocated path enforces is pinned in test_receipt_regression_pins.py; this file
proves only what the widening ADDS. The invoice helpers come from test_receivables.py (the pins'
precedent) so all three suites post the same invoice.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow
from app.core.exceptions import ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.finance import queries, service
from app.modules.finance.constants import (
    AR_PARTNER_TYPE,
    InvoiceStatus,
    ReceiptStatus,
)
from app.modules.finance.models import CustomerReceipt, JournalLine
from app.modules.finance.receivables_schemas import (
    CustomerReceiptCreate,
    ReceiptAllocationCreate,
)
from tests.modules.finance.conftest import ArSetup, FxSetup
from tests.modules.finance.factories import seed_advance_account
from tests.modules.finance.test_receivables import (
    _RECEIPT_DATE,
    _create_and_post_invoice,
    _invoice_payload,
)
from tests.modules.finance.test_receivables_fx import _R1_DATE, _R2_DATE, _post_eur_invoice


def _receipt(
    setup: ArSetup,
    *,
    partner_id: uuid.UUID,
    amount: str,
    allocations: list[ReceiptAllocationCreate] | None = None,
) -> CustomerReceiptCreate:
    return CustomerReceiptCreate(
        partner_id=partner_id,
        partner_name="Globex Inc",
        receipt_date=_RECEIPT_DATE,
        currency_code="USD",
        bank_account_id=setup.accounts["1000"],
        amount=Decimal(amount),
        allocations=[] if allocations is None else allocations,
    )


async def _post_receipt(
    session: AsyncSession, tenant_id: uuid.UUID, payload: CustomerReceiptCreate
) -> CustomerReceipt:
    holder: dict[str, uuid.UUID] = {}

    with tenant_context(tenant_id):

        async def work() -> None:
            receipt = await service.create_and_post_receipt(session, tenant_id, payload)
            holder["receipt_id"] = receipt.id

        await run_in_uow(session, work)
        return await service.get_customer_receipt(session, tenant_id, holder["receipt_id"])


async def _lines(
    session: AsyncSession, tenant_id: uuid.UUID, entry_id: uuid.UUID
) -> list[JournalLine]:
    with tenant_context(tenant_id):
        return list(
            (
                await session.execute(
                    select(JournalLine).where(JournalLine.journal_entry_id == entry_id)
                )
            )
            .scalars()
            .all()
        )


async def test_an_allocationless_receipt_posts_to_the_advance_control_with_partner_stamped(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    """A deposit taken before any invoice exists: Dr Bank / Cr Advance control, the credit line
    carrying partner_type + partner_id so the control reconciles per guest, and the whole amount
    standing as ``unapplied_amount``. No allocation, no invoice, no revenue."""
    advance_id = await seed_advance_account(db_session, ar_setup.tenant_id)
    partner_id = uuid.uuid4()

    receipt = await _post_receipt(
        db_session, ar_setup.tenant_id, _receipt(ar_setup, partner_id=partner_id, amount="500.00")
    )

    assert receipt.status == ReceiptStatus.POSTED.value
    assert receipt.receipt_number == "RCT-2026-00001"
    assert Decimal(str(receipt.unapplied_amount)) == Decimal("500.00")
    assert Decimal(str(receipt.amount)) == Decimal("500.00")

    lines = await _lines(db_session, ar_setup.tenant_id, receipt.journal_entry_id)
    assert len(lines) == 2
    bank_line = next(line for line in lines if line.account_id == ar_setup.accounts["1000"])
    advance_line = next(line for line in lines if line.account_id == advance_id)
    assert Decimal(str(bank_line.transaction_debit_amount)) == Decimal("500.00")
    assert Decimal(str(advance_line.transaction_credit_amount)) == Decimal("500.00")
    assert Decimal(str(advance_line.functional_credit_amount)) == Decimal("500.00")
    # The reconciliation key: the advance control is a POOLED liability, so a credit that does not
    # name its guest is a deposit nobody can find again.
    assert advance_line.partner_type == AR_PARTNER_TYPE
    assert advance_line.partner_id == partner_id


async def test_a_partially_allocated_receipt_splits_ar_and_advance(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    """500 received against a 300 invoice: 300 clears the invoice exactly as today (Cr AR control,
    invoice PAID, allocation row written) and the 200 excess lands on the advance control."""
    advance_id = await seed_advance_account(db_session, ar_setup.tenant_id)
    invoice = await _create_and_post_invoice(
        db_session, ar_setup, _invoice_payload(ar_setup, net="300.00")
    )

    receipt = await _post_receipt(
        db_session,
        ar_setup.tenant_id,
        _receipt(
            ar_setup,
            partner_id=invoice.partner_id,
            amount="500.00",
            allocations=[ReceiptAllocationCreate(invoice_id=invoice.id, amount=Decimal("300.00"))],
        ),
    )
    await db_session.refresh(invoice)

    assert invoice.status == InvoiceStatus.PAID.value
    assert Decimal(str(invoice.open_amount)) == Decimal("0.00")
    assert Decimal(str(receipt.unapplied_amount)) == Decimal("200.00")

    with tenant_context(ar_setup.tenant_id):
        allocations = await service.get_receipt_allocations(
            db_session, ar_setup.tenant_id, receipt.id
        )
    assert len(allocations) == 1
    assert Decimal(str(allocations[0].allocated_amount)) == Decimal("300.00")

    lines = await _lines(db_session, ar_setup.tenant_id, receipt.journal_entry_id)
    bank_line = next(line for line in lines if line.account_id == ar_setup.accounts["1000"])
    ar_line = next(line for line in lines if line.account_id == ar_setup.accounts["1200"])
    advance_line = next(line for line in lines if line.account_id == advance_id)
    assert Decimal(str(bank_line.transaction_debit_amount)) == Decimal("500.00")
    assert Decimal(str(ar_line.transaction_credit_amount)) == Decimal("300.00")
    assert Decimal(str(advance_line.transaction_credit_amount)) == Decimal("200.00")
    debit = sum((Decimal(str(line.functional_debit_amount)) for line in lines), Decimal(0))
    credit = sum((Decimal(str(line.functional_credit_amount)) for line in lines), Decimal(0))
    assert debit == credit == Decimal("500.00")


async def test_apply_receipt_moves_unapplied_to_a_posted_invoice(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    """The reclass, proven in FOREIGN currency because that is where "reuses clearing_fx" is a
    claim with digits behind it: a EUR deposit taken at SPOT 1.20 and applied to an invoice frozen
    at 1.10 must produce the SAME functional numbers as a direct allocation of the same amounts —
    AR cleared at the invoice's rate, the advance leg reversed at the rate it was booked at, the
    difference realized. A reclass that re-rated the AR side, or skipped the FX line, would still
    balance and still clear the invoice; only the digits catch it."""
    advance_id = await seed_advance_account(db_session, fx_setup.tenant_id)
    deposited = await _post_eur_invoice(db_session, fx_setup)  # the invoice the deposit will pay
    direct = await _post_eur_invoice(db_session, fx_setup)  # the same invoice, cleared directly

    def _eur_receipt(partner_id: uuid.UUID, allocations: list[ReceiptAllocationCreate]):
        return CustomerReceiptCreate(
            partner_id=partner_id,
            partner_name="Euro Customer",
            receipt_date=_R2_DATE,
            currency_code="EUR",
            bank_account_id=fx_setup.eur_bank_id,
            amount=Decimal("100.00"),
            allocations=allocations,
        )

    deposit = await _post_receipt(
        db_session, fx_setup.tenant_id, _eur_receipt(deposited.partner_id, [])
    )
    assert Decimal(str(deposit.unapplied_amount)) == Decimal("100.00")

    with tenant_context(fx_setup.tenant_id):

        async def apply() -> None:
            await service.apply_receipt(
                db_session,
                fx_setup.tenant_id,
                deposit.id,
                [ReceiptAllocationCreate(invoice_id=deposited.id, amount=Decimal("100.00"))],
            )

        await run_in_uow(db_session, apply)

    direct_receipt = await _post_receipt(
        db_session,
        fx_setup.tenant_id,
        _eur_receipt(
            direct.partner_id,
            [ReceiptAllocationCreate(invoice_id=direct.id, amount=Decimal("100.00"))],
        ),
    )

    await db_session.refresh(deposit)
    await db_session.refresh(deposited)
    assert Decimal(str(deposit.unapplied_amount)) == Decimal("0.00")
    assert deposited.status == InvoiceStatus.PAID.value
    assert Decimal(str(deposited.open_amount)) == Decimal("0.00")
    # The reclass posts its OWN entry — a posted entry is immutable (D-017), so the deposit's entry
    # is untouched and the application is the entry that DEBITS the advance control.
    with tenant_context(fx_setup.tenant_id):
        reclass_entry_id = (
            await db_session.execute(
                select(JournalLine.journal_entry_id).where(
                    JournalLine.account_id == advance_id,
                    JournalLine.functional_debit_amount > 0,
                )
            )
        ).scalar_one()
    assert reclass_entry_id != deposit.journal_entry_id

    reclass = await _lines(db_session, fx_setup.tenant_id, reclass_entry_id)
    straight = await _lines(db_session, fx_setup.tenant_id, direct_receipt.journal_entry_id)

    def _by_account(lines: list[JournalLine]) -> dict[uuid.UUID, tuple[Decimal, Decimal]]:
        return {
            line.account_id: (
                Decimal(str(line.functional_debit_amount)),
                Decimal(str(line.functional_credit_amount)),
            )
            for line in lines
        }

    reclass_by_account = _by_account(reclass)
    straight_by_account = _by_account(straight)
    ar_control = fx_setup.accounts["1900"]
    fx_gain = fx_setup.accounts["7100"]
    # EUR 100 at the invoice's frozen 1.10 = USD 110 off the AR control, the cash leg at the
    # receipt-date 1.20 = USD 120, and USD 10 realized — identical in both entries.
    assert reclass_by_account[ar_control] == straight_by_account[ar_control]
    assert reclass_by_account[ar_control] == (Decimal(0), Decimal("110.00"))
    assert reclass_by_account[fx_gain] == straight_by_account[fx_gain]
    assert reclass_by_account[fx_gain] == (Decimal(0), Decimal("10.00"))
    # The only difference is WHICH account carries the debit: the advance control, not the bank.
    assert reclass_by_account[advance_id] == straight_by_account[fx_setup.eur_bank_id]
    assert reclass_by_account[advance_id] == (Decimal("120.00"), Decimal(0))
    assert fx_setup.eur_bank_id not in reclass_by_account
    advance_line = next(line for line in reclass if line.account_id == advance_id)
    assert advance_line.partner_type == AR_PARTNER_TYPE
    assert advance_line.partner_id == deposited.partner_id
    assert _R1_DATE < _R2_DATE  # the rates the assertions above are built on


async def test_an_advance_line_keeps_the_entry_currency_when_there_is_no_fx_line(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    """The regression the widening could have caused silently. ``set_fx_line_currency`` used to
    re-denominate "the third line" in the functional currency, which was safe only while a clearing
    entry was exactly control + bank + FX. A foreign receipt whose invoice rate equals its receipt
    rate posts NO FX line, so with an unapplied excess the third line is the ADVANCE credit — and
    stamping USD on a EUR liability line would misstate what the property owes the guest, on an
    entry that still balances. The line is now found by its description instead."""
    advance_id = await seed_advance_account(db_session, fx_setup.tenant_id)
    invoice = await _post_eur_invoice(db_session, fx_setup)  # posted at _R1_DATE, SPOT 1.10

    receipt = await _post_receipt(
        db_session,
        fx_setup.tenant_id,
        CustomerReceiptCreate(
            partner_id=invoice.partner_id,
            partner_name="Euro Customer",
            receipt_date=_R1_DATE,  # the SAME rate the invoice froze: no realized FX
            currency_code="EUR",
            bank_account_id=fx_setup.eur_bank_id,
            amount=Decimal("150.00"),
            allocations=[ReceiptAllocationCreate(invoice_id=invoice.id, amount=Decimal("100.00"))],
        ),
    )

    assert Decimal(str(receipt.unapplied_amount)) == Decimal("50.00")
    lines = await _lines(db_session, fx_setup.tenant_id, receipt.journal_entry_id)
    assert len(lines) == 3  # AR control, bank, advance — no FX line
    advance_line = next(line for line in lines if line.account_id == advance_id)
    assert advance_line.currency_code == "EUR"
    assert Decimal(str(advance_line.transaction_credit_amount)) == Decimal("50.00")
    assert Decimal(str(advance_line.functional_credit_amount)) == Decimal("55.00")  # 50 x 1.10


async def test_apply_receipt_refuses_more_than_the_unapplied_balance(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    """The mirror of finance.receipt_overallocated on the other side of the receipt: a deposit can
    only be spent once, so applying 600 of a 500 deposit is refused before anything posts."""
    await seed_advance_account(db_session, ar_setup.tenant_id)
    invoice = await _create_and_post_invoice(
        db_session, ar_setup, _invoice_payload(ar_setup, net="600.00")
    )
    deposit = await _post_receipt(
        db_session,
        ar_setup.tenant_id,
        _receipt(ar_setup, partner_id=invoice.partner_id, amount="500.00"),
    )

    with tenant_context(ar_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.apply_receipt(
            db_session,
            ar_setup.tenant_id,
            deposit.id,
            [ReceiptAllocationCreate(invoice_id=invoice.id, amount=Decimal("600.00"))],
        )
    assert exc.value.code == "finance.receipt_apply_exceeds_unapplied"
    await db_session.refresh(deposit)
    assert Decimal(str(deposit.unapplied_amount)) == Decimal("500.00")


async def test_apply_receipt_refuses_a_cross_partner_invoice(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    """One guest's deposit never pays another guest's bill: apply runs the SAME validation as
    create, so the invoice must belong to the receipt's partner."""
    await seed_advance_account(db_session, ar_setup.tenant_id)
    other_invoice = await _create_and_post_invoice(db_session, ar_setup, _invoice_payload(ar_setup))
    deposit = await _post_receipt(
        db_session, ar_setup.tenant_id, _receipt(ar_setup, partner_id=uuid.uuid4(), amount="500.00")
    )

    with tenant_context(ar_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.apply_receipt(
            db_session,
            ar_setup.tenant_id,
            deposit.id,
            [ReceiptAllocationCreate(invoice_id=other_invoice.id, amount=Decimal("100.00"))],
        )
    assert exc.value.code == "finance.receipt_partner_mismatch"


async def test_over_allocation_is_still_refused(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    """The half of the ``==`` rule that does NOT relax: ``amount >= sum(allocations)``. Allocating
    cash the receipt never received is issue #73 with the sign flipped — the difference would flow
    into the realized-FX line as a phantom gain — so it stays a 422, and there is no such thing as
    a negative unapplied balance."""
    invoice = await _create_and_post_invoice(db_session, ar_setup, _invoice_payload(ar_setup))
    with tenant_context(ar_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_and_post_receipt(
            db_session,
            ar_setup.tenant_id,
            _receipt(
                ar_setup,
                partner_id=invoice.partner_id,
                amount="40.00",
                allocations=[
                    ReceiptAllocationCreate(invoice_id=invoice.id, amount=Decimal("60.00"))
                ],
            ),
        )
    assert exc.value.code == "finance.receipt_allocation_sum_mismatch"


async def test_partner_ledger_shows_the_unapplied_balance(
    db_session: AsyncSession, ar_setup: ArSetup
) -> None:
    """``partner_ledger`` derives from ROWS, not journal lines, so a deposit that posted a perfect
    journal is still invisible to AR unless the ledger reads it. The on-account balance is a
    SEPARATE number from the open-invoice balance (a deposit is a liability, not a negative
    receivable), and it drops as the deposit is applied."""
    await seed_advance_account(db_session, ar_setup.tenant_id)
    invoice = await _create_and_post_invoice(
        db_session, ar_setup, _invoice_payload(ar_setup, net="300.00")
    )
    partner_id = invoice.partner_id
    deposit = await _post_receipt(
        db_session, ar_setup.tenant_id, _receipt(ar_setup, partner_id=partner_id, amount="500.00")
    )

    with tenant_context(ar_setup.tenant_id):
        unapplied = await queries.customer_unapplied_balance(
            db_session, ar_setup.tenant_id, partner_id
        )
        owed = await queries.customer_open_balance(db_session, ar_setup.tenant_id, partner_id)
    assert unapplied == Decimal("500.00")
    assert owed == Decimal("300.00")

    with tenant_context(ar_setup.tenant_id):

        async def apply() -> None:
            await service.apply_receipt(
                db_session,
                ar_setup.tenant_id,
                deposit.id,
                [ReceiptAllocationCreate(invoice_id=invoice.id, amount=Decimal("300.00"))],
            )

        await run_in_uow(db_session, apply)
        unapplied = await queries.customer_unapplied_balance(
            db_session, ar_setup.tenant_id, partner_id
        )
        owed = await queries.customer_open_balance(db_session, ar_setup.tenant_id, partner_id)
    assert unapplied == Decimal("200.00")
    assert owed == Decimal("0.00")

    # Another partner's deposit is not this partner's on-account money.
    with tenant_context(ar_setup.tenant_id):
        assert await queries.customer_unapplied_balance(
            db_session, ar_setup.tenant_id, uuid.uuid4()
        ) == Decimal(0)
