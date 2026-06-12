"""Accounts Payable service + API behaviour (PLAN 4.5, D-029), SQLite.

Proves the bill -> post -> pay flow, open-item clearing, the payment run, aging projection,
idempotent posting/payment, RBAC, and tenant isolation — all single-functional-currency here.
Realized FX at clearing (D-019) is proven separately in test_payables_fx.py.
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
    AP_PARTNER_TYPE,
    BillStatus,
    PaymentStatus,
)
from app.modules.finance.events import VendorBillPosted, VendorPaymentPosted
from app.modules.finance.models import (
    JournalLine,
    VendorBill,
    VendorPaymentAllocation,
)
from app.modules.finance.payables_schemas import (
    PaymentAllocationCreate,
    VendorBillCreate,
    VendorBillLineCreate,
    VendorPaymentCreate,
)
from tests.modules.finance.conftest import ApSetup

_BILL_DATE = date(2026, 3, 1)
_DUE_DATE = date(2026, 3, 31)
_PAY_DATE = date(2026, 3, 15)


def _bill_payload(
    setup: ApSetup,
    *,
    net: str = "100.00",
    with_tax: bool = False,
    partner_id: uuid.UUID | None = None,
    partner_name: str = "Acme Supplies",
    due_date: date = _DUE_DATE,
) -> VendorBillCreate:
    return VendorBillCreate(
        partner_id=partner_id or uuid.uuid4(),
        partner_name=partner_name,
        bill_date=_BILL_DATE,
        due_date=due_date,
        currency_code="USD",
        ap_account_id=setup.accounts["2000"],
        description="Office supplies",
        lines=[
            VendorBillLineCreate(
                account_id=setup.accounts["5000"],
                net_amount=Decimal(net),
                tax_code_id=setup.tax_code_id if with_tax else None,
            )
        ],
    )


async def _create_and_post_bill(
    session: AsyncSession,
    setup: ApSetup,
    payload: VendorBillCreate,
) -> VendorBill:
    with tenant_context(setup.tenant_id):
        bill = await service.create_vendor_bill(session, setup.tenant_id, payload)
        await session.commit()

        async def work() -> None:
            await service.post_vendor_bill(session, setup.tenant_id, bill.id)

        await run_in_uow(session, work)
        await session.refresh(bill)
    return bill


# --- bill create + post -------------------------------------------------------


async def test_post_bill_builds_balanced_journal(
    db_session: AsyncSession, ap_setup: ApSetup
) -> None:
    captured: list[VendorBillPosted] = []

    async def _capture(_s: AsyncSession, event: VendorBillPosted) -> None:
        captured.append(event)

    subscribe(VendorBillPosted.key, _capture)
    bill = await _create_and_post_bill(db_session, ap_setup, _bill_payload(ap_setup))

    assert bill.status == BillStatus.POSTED.value
    assert bill.bill_number == "BILL-2026-00001"
    assert bill.journal_entry_id is not None
    assert Decimal(str(bill.open_amount)) == Decimal("100.00")
    assert Decimal(str(bill.gross_amount)) == Decimal("100.00")

    with tenant_context(ap_setup.tenant_id):
        lines = (
            await db_session.execute(
                select(JournalLine).where(JournalLine.journal_entry_id == bill.journal_entry_id)
            )
        ).scalars().all()
    debit = sum((Decimal(str(line.functional_debit_amount)) for line in lines), Decimal(0))
    credit = sum((Decimal(str(line.functional_credit_amount)) for line in lines), Decimal(0))
    assert debit == credit == Decimal("100.00")
    # The AP control line carries the opaque partner_id (D-029).
    ap_line = next(line for line in lines if line.account_id == ap_setup.accounts["2000"])
    assert Decimal(str(ap_line.transaction_credit_amount)) == Decimal("100.00")
    assert ap_line.partner_id == bill.partner_id
    assert ap_line.partner_type == AP_PARTNER_TYPE
    # Event fired with the bill totals.
    assert len(captured) == 1
    assert captured[0].bill_id == bill.id
    assert captured[0].gross_amount == Decimal("100.00")


async def test_post_bill_with_tax_posts_to_receivable_account(
    db_session: AsyncSession, ap_setup: ApSetup
) -> None:
    bill = await _create_and_post_bill(
        db_session, ap_setup, _bill_payload(ap_setup, net="100.00", with_tax=True)
    )
    # gross = net + tax = 100 + 20.
    assert Decimal(str(bill.net_amount)) == Decimal("100.00")
    assert Decimal(str(bill.tax_amount)) == Decimal("20.00")
    assert Decimal(str(bill.gross_amount)) == Decimal("120.00")
    assert Decimal(str(bill.open_amount)) == Decimal("120.00")

    with tenant_context(ap_setup.tenant_id):
        lines = (
            await db_session.execute(
                select(JournalLine).where(JournalLine.journal_entry_id == bill.journal_entry_id)
            )
        ).scalars().all()
    tax_line = next(line for line in lines if line.account_id == ap_setup.accounts["6000"])
    assert Decimal(str(tax_line.transaction_debit_amount)) == Decimal("20.00")
    ap_line = next(line for line in lines if line.account_id == ap_setup.accounts["2000"])
    assert Decimal(str(ap_line.transaction_credit_amount)) == Decimal("120.00")


async def test_create_bill_requires_lines(
    db_session: AsyncSession, ap_setup: ApSetup
) -> None:
    payload = _bill_payload(ap_setup)
    payload.lines = []
    with tenant_context(ap_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_vendor_bill(db_session, ap_setup.tenant_id, payload)
    assert exc.value.code == "finance.vendor_bill_no_lines"


# --- payment clearing ---------------------------------------------------------


async def _pay_bill(
    session: AsyncSession,
    setup: ApSetup,
    bill: VendorBill,
    amount: str,
) -> uuid.UUID:
    captured: list[VendorPaymentPosted] = []

    async def _capture(_s: AsyncSession, event: VendorPaymentPosted) -> None:
        captured.append(event)

    subscribe(VendorPaymentPosted.key, _capture)
    holder: dict[str, uuid.UUID] = {}
    with tenant_context(setup.tenant_id):
        async def work() -> None:
            payment = await service.create_and_post_payment(
                session,
                setup.tenant_id,
                VendorPaymentCreate(
                    partner_id=bill.partner_id,
                    partner_name=bill.partner_name,
                    payment_date=_PAY_DATE,
                    currency_code="USD",
                    bank_account_id=setup.accounts["1000"],
                    amount=Decimal(amount),
                    allocations=[PaymentAllocationCreate(bill_id=bill.id, amount=Decimal(amount))],
                ),
            )
            holder["id"] = payment.id

        await run_in_uow(session, work)
        await session.refresh(bill)
    assert len(captured) == 1
    return holder["id"]


async def test_full_payment_clears_bill(
    db_session: AsyncSession, ap_setup: ApSetup
) -> None:
    bill = await _create_and_post_bill(db_session, ap_setup, _bill_payload(ap_setup))
    payment_id = await _pay_bill(db_session, ap_setup, bill, "100.00")

    assert bill.status == BillStatus.PAID.value
    assert Decimal(str(bill.open_amount)) == Decimal("0.00")

    with tenant_context(ap_setup.tenant_id):
        allocations = (
            await db_session.execute(
                select(VendorPaymentAllocation).where(
                    VendorPaymentAllocation.payment_id == payment_id
                )
            )
        ).scalars().all()
        payment = await service.get_vendor_payment(db_session, ap_setup.tenant_id, payment_id)
        lines = (
            await db_session.execute(
                select(JournalLine).where(JournalLine.journal_entry_id == payment.journal_entry_id)
            )
        ).scalars().all()
    assert len(allocations) == 1
    assert Decimal(str(allocations[0].allocated_amount)) == Decimal("100.00")
    # Dr AP / Cr bank, balanced.
    debit = sum((Decimal(str(line.functional_debit_amount)) for line in lines), Decimal(0))
    credit = sum((Decimal(str(line.functional_credit_amount)) for line in lines), Decimal(0))
    assert debit == credit == Decimal("100.00")
    ap_line = next(line for line in lines if line.account_id == ap_setup.accounts["2000"])
    bank_line = next(line for line in lines if line.account_id == ap_setup.accounts["1000"])
    assert Decimal(str(ap_line.transaction_debit_amount)) == Decimal("100.00")
    assert Decimal(str(bank_line.transaction_credit_amount)) == Decimal("100.00")


async def test_partial_payment_reduces_open_amount(
    db_session: AsyncSession, ap_setup: ApSetup
) -> None:
    bill = await _create_and_post_bill(db_session, ap_setup, _bill_payload(ap_setup))
    await _pay_bill(db_session, ap_setup, bill, "40.00")
    assert bill.status == BillStatus.PARTIALLY_PAID.value
    assert Decimal(str(bill.open_amount)) == Decimal("60.00")


async def test_cannot_pay_a_draft_bill(
    db_session: AsyncSession, ap_setup: ApSetup
) -> None:
    with tenant_context(ap_setup.tenant_id):
        bill = await service.create_vendor_bill(
            db_session, ap_setup.tenant_id, _bill_payload(ap_setup)
        )
        await db_session.commit()
        with pytest.raises(ConflictError) as exc:
            await service.create_and_post_payment(
                db_session,
                ap_setup.tenant_id,
                VendorPaymentCreate(
                    partner_id=bill.partner_id,
                    partner_name=bill.partner_name,
                    payment_date=_PAY_DATE,
                    currency_code="USD",
                    bank_account_id=ap_setup.accounts["1000"],
                    amount=Decimal("100.00"),
                    allocations=[
                        PaymentAllocationCreate(bill_id=bill.id, amount=Decimal("100.00"))
                    ],
                ),
            )
    assert exc.value.code == "finance.bill_not_open"


async def test_cannot_overpay_a_bill(
    db_session: AsyncSession, ap_setup: ApSetup
) -> None:
    bill = await _create_and_post_bill(db_session, ap_setup, _bill_payload(ap_setup))
    with tenant_context(ap_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_and_post_payment(
            db_session,
            ap_setup.tenant_id,
            VendorPaymentCreate(
                partner_id=bill.partner_id,
                partner_name=bill.partner_name,
                payment_date=_PAY_DATE,
                currency_code="USD",
                bank_account_id=ap_setup.accounts["1000"],
                amount=Decimal("150.00"),
                allocations=[PaymentAllocationCreate(bill_id=bill.id, amount=Decimal("150.00"))],
            ),
        )
    assert exc.value.code == "finance.payment_overallocated"


# --- payment run --------------------------------------------------------------


async def test_payment_run_groups_by_partner(
    db_session: AsyncSession, ap_setup: ApSetup
) -> None:
    partner_a = uuid.uuid4()
    partner_b = uuid.uuid4()
    # 3 due bills: two for partner A, one for partner B.
    await _create_and_post_bill(
        db_session, ap_setup, _bill_payload(ap_setup, net="50.00", partner_id=partner_a)
    )
    await _create_and_post_bill(
        db_session, ap_setup, _bill_payload(ap_setup, net="30.00", partner_id=partner_a)
    )
    await _create_and_post_bill(
        db_session, ap_setup, _bill_payload(ap_setup, net="70.00", partner_id=partner_b)
    )
    holder: dict[str, list] = {}
    with tenant_context(ap_setup.tenant_id):
        async def work() -> None:
            holder["payments"] = await service.run_payment_batch(
                db_session,
                ap_setup.tenant_id,
                up_to_due_date=_DUE_DATE,
                bank_account_id=ap_setup.accounts["1000"],
            )

        await run_in_uow(db_session, work)
        # All three bills paid in full.
        bills = (
            await db_session.execute(
                select(VendorBill).where(VendorBill.tenant_id == ap_setup.tenant_id)
            )
        ).scalars().all()
    assert len(holder["payments"]) == 2  # one payment per partner
    assert all(b.status == BillStatus.PAID.value for b in bills)
    amounts = sorted(Decimal(str(p.amount)) for p in holder["payments"])
    assert amounts == [Decimal("70.00"), Decimal("80.00")]


async def test_payment_run_skips_bills_not_yet_due(
    db_session: AsyncSession, ap_setup: ApSetup
) -> None:
    # A bill due AFTER the run date is not paid.
    await _create_and_post_bill(
        db_session,
        ap_setup,
        _bill_payload(ap_setup, due_date=date(2026, 6, 30)),
    )
    with tenant_context(ap_setup.tenant_id):
        async def work() -> None:
            payments = await service.run_payment_batch(
                db_session,
                ap_setup.tenant_id,
                up_to_due_date=date(2026, 3, 31),
                bank_account_id=ap_setup.accounts["1000"],
            )
            assert payments == []

        await run_in_uow(db_session, work)


# --- aging --------------------------------------------------------------------


async def test_aging_buckets_by_days_overdue(
    db_session: AsyncSession, ap_setup: ApSetup
) -> None:
    # Three bills due on different dates; aging as of 2026-04-15.
    await _create_and_post_bill(
        db_session, ap_setup, _bill_payload(ap_setup, net="10.00", due_date=date(2026, 4, 30))
    )  # not yet due -> current
    await _create_and_post_bill(
        db_session, ap_setup, _bill_payload(ap_setup, net="20.00", due_date=date(2026, 4, 1))
    )  # 14 days overdue -> 1-30
    await _create_and_post_bill(
        db_session, ap_setup, _bill_payload(ap_setup, net="30.00", due_date=date(2026, 3, 1))
    )  # 45 days overdue -> 31-60
    with tenant_context(ap_setup.tenant_id):
        report = await service.vendor_aging(db_session, ap_setup.tenant_id, date(2026, 4, 15))
    assert report["current"] == Decimal("10.00")
    assert report["days_1_30"] == Decimal("20.00")
    assert report["days_31_60"] == Decimal("30.00")
    assert report["total"] == Decimal("60.00")


async def test_aging_as_of_in_the_past_shifts_buckets(
    db_session: AsyncSession, ap_setup: ApSetup
) -> None:
    await _create_and_post_bill(
        db_session, ap_setup, _bill_payload(ap_setup, net="30.00", due_date=date(2026, 3, 1))
    )
    with tenant_context(ap_setup.tenant_id):
        # As of the due date -> current (not overdue).
        on_due = await service.vendor_aging(db_session, ap_setup.tenant_id, date(2026, 3, 1))
        # 45 days later -> 31-60.
        later = await service.vendor_aging(db_session, ap_setup.tenant_id, date(2026, 4, 15))
    assert on_due["current"] == Decimal("30.00")
    assert on_due["days_31_60"] == Decimal("0.00")
    assert later["current"] == Decimal("0.00")
    assert later["days_31_60"] == Decimal("30.00")


async def test_open_vendor_bills_query(
    db_session: AsyncSession, ap_setup: ApSetup
) -> None:
    partner = uuid.uuid4()
    bill = await _create_and_post_bill(
        db_session, ap_setup, _bill_payload(ap_setup, partner_id=partner)
    )
    with tenant_context(ap_setup.tenant_id):
        open_bills = await queries.get_open_vendor_bills(db_session, ap_setup.tenant_id, partner)
    assert [b.id for b in open_bills] == [bill.id]


# --- idempotency --------------------------------------------------------------


async def test_post_bill_is_idempotent(
    db_session: AsyncSession, ap_setup: ApSetup
) -> None:
    with tenant_context(ap_setup.tenant_id):
        bill = await service.create_vendor_bill(
            db_session, ap_setup.tenant_id, _bill_payload(ap_setup)
        )
        await db_session.commit()

        async def work() -> None:
            await service.post_vendor_bill(db_session, ap_setup.tenant_id, bill.id)

        await run_in_uow(db_session, work)
        await db_session.refresh(bill)
        first_number = bill.bill_number
        # A second post returns the same bill unchanged (no second number).
        await service.post_vendor_bill(db_session, ap_setup.tenant_id, bill.id)
        await db_session.refresh(bill)
    assert bill.bill_number == first_number
    assert bill.status == BillStatus.POSTED.value


async def test_payment_status_is_posted(
    db_session: AsyncSession, ap_setup: ApSetup
) -> None:
    bill = await _create_and_post_bill(db_session, ap_setup, _bill_payload(ap_setup))
    payment_id = await _pay_bill(db_session, ap_setup, bill, "100.00")
    with tenant_context(ap_setup.tenant_id):
        payment = await service.get_vendor_payment(db_session, ap_setup.tenant_id, payment_id)
    assert payment.status == PaymentStatus.POSTED.value
    assert payment.payment_number == "PAY-2026-00001"


# --- tenant isolation ---------------------------------------------------------


async def test_bill_is_tenant_isolated(
    db_session: AsyncSession, ap_setup: ApSetup, tenant_b: uuid.UUID
) -> None:
    bill = await _create_and_post_bill(db_session, ap_setup, _bill_payload(ap_setup))
    from app.core.exceptions import NotFoundError

    with tenant_context(tenant_b), pytest.raises(NotFoundError):
        await service.get_vendor_bill(db_session, tenant_b, bill.id)
