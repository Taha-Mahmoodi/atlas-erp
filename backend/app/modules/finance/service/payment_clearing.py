"""Open-item clearing + realized-FX line construction for vendor payments (PLAN 4.5, D-019).

Split out of ``vendor_payments.py`` to keep both under the STRUCTURE §3 400-line cap: this file is
the clearing/FX MATH (validate the allocations, derive each bill's frozen rate, build the balanced
journal lines with explicit functional amounts, then stamp those functional amounts onto the draft
lines), while ``vendor_payments.py`` orchestrates the payment document, numbering, allocations and
events around it. Reused by AR clearing later (same realized-FX shape at the customer side).

Realized FX (D-019): the AP control was credited at each bill's posting-date rate (R1); the bank
pays at the payment-date rate (R2). ``functional-at-bill-rate − functional-at-payment-rate`` over
each cleared amount is the realized gain/loss, posted to the fx_realized_gain/loss posting-default
account INSIDE the same entry so it balances in functional. When the payment currency IS functional,
R1 == R2 == 1 and there is no FX line.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.money import currency_decimals, quantize_money
from app.modules.finance.constants import (
    FX_REALIZED_GAIN,
    FX_REALIZED_LOSS,
    BillStatus,
    RateKind,
)
from app.modules.finance.models import Account, VendorBill
from app.modules.finance.payables_schemas import PaymentAllocationCreate
from app.modules.finance.schemas import JournalLineCreate
from app.modules.finance.service import fx
from app.modules.finance.service.journal_read import load_lines
from app.modules.finance.service.posting_defaults import get_posting_default


async def require_bank_account(
    session: AsyncSession, tenant_id: uuid.UUID, account_id: uuid.UUID
) -> Account:
    account = (
        await session.execute(
            select(Account).where(Account.tenant_id == tenant_id, Account.id == account_id)
        )
    ).scalar_one_or_none()
    if account is None:
        raise ValidationFailedError(
            message="The bank account does not exist in this tenant",
            code="finance.ap_bank_account_not_found",
            details={"account_id": str(account_id)},
        )
    return account


async def validated_clearing(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    partner_id: uuid.UUID,
    currency_code: str,
    allocations: list[PaymentAllocationCreate],
) -> list[tuple[VendorBill, Decimal]]:
    """Validate every allocation clears an OPEN bill of this partner + currency, by no more than
    the bill's open amount, and return the (bill, allocated) pairs (PLAN 4.5). Clear 422/409."""
    if not allocations:
        raise ValidationFailedError(
            message="A payment must clear at least one bill",
            code="finance.payment_no_allocations",
        )
    pairs: list[tuple[VendorBill, Decimal]] = []
    for alloc in allocations:
        bill = await session.get(VendorBill, alloc.bill_id)
        if bill is None or bill.tenant_id != tenant_id:
            raise ValidationFailedError(
                message="A payment allocation references an unknown bill",
                code="finance.vendor_bill_not_found",
                details={"bill_id": str(alloc.bill_id)},
            )
        if bill.status not in (BillStatus.POSTED.value, BillStatus.PARTIALLY_PAID.value):
            raise ConflictError(
                message="Only a posted, open bill can be paid",
                code="finance.bill_not_open",
                details={"bill_id": str(bill.id), "status": bill.status},
            )
        if bill.partner_id != partner_id:
            raise ValidationFailedError(
                message="All bills in a payment must belong to the same partner",
                code="finance.payment_partner_mismatch",
                details={"bill_id": str(bill.id)},
            )
        if bill.currency_code != currency_code:
            raise ValidationFailedError(
                message="All bills in a payment must share the payment currency",
                code="finance.payment_currency_mismatch",
                details={"bill_id": str(bill.id), "currency_code": bill.currency_code},
            )
        amount = quantize_money(alloc.amount, currency_decimals(currency_code))
        if amount <= 0:
            raise ValidationFailedError(
                message="An allocation amount must be positive",
                code="finance.payment_allocation_not_positive",
                details={"bill_id": str(bill.id)},
            )
        if amount > Decimal(str(bill.open_amount)):
            raise ValidationFailedError(
                message="An allocation cannot exceed the bill's open amount",
                code="finance.payment_overallocated",
                details={"bill_id": str(bill.id), "open_amount": str(bill.open_amount)},
            )
        pairs.append((bill, amount))
    return pairs


async def _bill_frozen_functional(
    session: AsyncSession, tenant_id: uuid.UUID, bill: VendorBill
) -> Decimal:
    """The functional amount credited to the AP control when ``bill`` was posted (D-019). Read from
    the bill's AP-control journal line (the line on ``bill.ap_account_id``), so the frozen rate
    comes from the actual posting, not a re-lookup. Used to derive the per-bill clearing rate."""
    lines = await load_lines(session, tenant_id, bill.journal_entry_id)
    for line in lines:
        if line.account_id == bill.ap_account_id and line.functional_credit_amount > 0:
            return Decimal(str(line.functional_credit_amount))
    # A functional == transaction (single-currency) bill: the credited functional equals gross.
    return Decimal(str(bill.gross_amount))


async def build_payment_lines(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    pairs: list[tuple[VendorBill, Decimal]],
    *,
    currency_code: str,
    bank_account_id: uuid.UUID,
    payment_amount: Decimal,
    payment_date: date,
) -> tuple[list[JournalLineCreate], list[tuple[Decimal, Decimal]]]:
    """Build the balanced payment journal lines + their explicit functional (debit, credit) amounts
    (D-019), aligned by index. The AP control clears each bill at its frozen rate; the bank pays at
    the payment-date rate; the realized FX line absorbs the functional difference so the entry
    balances in functional. The realized-FX line is functional-valued but carries a positive
    transaction side so the per-line one-side CHECK holds (D-017); the entry need not balance in
    TRANSACTION terms (mixed currencies), only in functional — ``create_draft_entry`` checks the
    functional sums when ``functional_amounts`` is supplied, and ``post_entry`` runs with
    ``skip_translation``.
    """
    func_code = await fx.functional_currency_or_none(session, tenant_id)
    func_decimals = currency_decimals(func_code) if func_code else currency_decimals(currency_code)
    is_foreign = func_code is not None and currency_code != func_code

    cleared_total = sum((amount for _bill, amount in pairs), Decimal(0))
    ap_account_id = pairs[0][0].ap_account_id
    partner_id = pairs[0][0].partner_id

    payment_rate = (
        await fx.get_rate(session, tenant_id, currency_code, func_code, payment_date, RateKind.SPOT)
        if is_foreign
        else Decimal(1)
    )
    func_ap = Decimal(0)
    for bill, amount in pairs:
        if is_foreign:
            frozen_functional = await _bill_frozen_functional(session, tenant_id, bill)
            bill_rate = frozen_functional / Decimal(str(bill.gross_amount))
            func_ap += quantize_money(amount * bill_rate, func_decimals)
        else:
            func_ap += amount
    func_bank = quantize_money(payment_amount * payment_rate, func_decimals)

    lines: list[JournalLineCreate] = [
        JournalLineCreate(
            account_id=ap_account_id,
            description="AP clearing",
            transaction_debit_amount=cleared_total,
            partner_id=partner_id,
        ),
        JournalLineCreate(
            account_id=bank_account_id,
            description="Bank payment",
            transaction_credit_amount=payment_amount,
        ),
    ]
    functional_amounts: list[tuple[Decimal, Decimal]] = [
        (func_ap, Decimal(0)),
        (Decimal(0), func_bank),
    ]

    realized = func_ap - func_bank
    if realized != 0:
        # Positive realized = AP functional owed MORE than paid -> a GAIN (credit); negative -> a
        # LOSS (debit). The FX line carries a positive transaction side equal to its functional
        # amount so the per-line one-side CHECK holds (D-017).
        amount = abs(realized)
        purpose = FX_REALIZED_GAIN if realized > 0 else FX_REALIZED_LOSS
        fx_account_id = await get_posting_default(session, tenant_id, purpose)
        if realized > 0:
            lines.append(
                JournalLineCreate(
                    account_id=fx_account_id,
                    description="Realized FX gain",
                    transaction_credit_amount=amount,
                )
            )
            functional_amounts.append((Decimal(0), amount))
        else:
            lines.append(
                JournalLineCreate(
                    account_id=fx_account_id,
                    description="Realized FX loss",
                    transaction_debit_amount=amount,
                )
            )
            functional_amounts.append((amount, Decimal(0)))
    return lines, functional_amounts


async def set_fx_line_currency(
    session: AsyncSession, tenant_id: uuid.UUID, entry_id: uuid.UUID
) -> None:
    """Denominate the realized-FX line (the 3rd line, if any) in the functional currency (D-019) —
    it is a functional gain/loss, not a foreign cash flow. Cosmetic vs the entry currency on the
    line; mutate the loaded object so the change is captured. No-op when no FX line exists."""
    func_code = await fx.functional_currency_or_none(session, tenant_id)
    if func_code is None:
        return
    lines = await load_lines(session, tenant_id, entry_id)
    if len(lines) >= 3:
        lines[2].currency_code = func_code
        await session.flush()
