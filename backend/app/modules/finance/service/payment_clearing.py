"""Open-item validation for vendor payments (PLAN 4.5) over the shared clearing-FX helper (D-019).

The realized-FX MATH lives in ``clearing_fx.py`` (shared with AR receipts since PLAN 4.6); this
file keeps only the AP-SPECIFIC parts: validate each allocation clears an OPEN bill of the right
partner + currency, and adapt those bills into the shared ``ClearedItem`` tuples the builder
consumes. ``vendor_payments.py`` orchestrates the payment document, numbering, allocations + events.

Realized FX (D-019): the AP control was credited at each bill's posting-date rate (R1); the bank
pays at the payment-date rate (R2). The shared builder books ``functional-at-bill-rate −
functional-at-payment-rate`` over each cleared amount to the fx_realized_gain/loss account inside
the payment entry so it balances in functional. AP debits the control to clear (Dr AP / Cr bank);
the bill's frozen functional comes from the CREDIT side of its posting line.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.money import currency_decimals, quantize_money
from app.modules.finance.constants import BillStatus
from app.modules.finance.models import Account, VendorBill
from app.modules.finance.payables_schemas import PaymentAllocationCreate
from app.modules.finance.schemas import JournalLineCreate
from app.modules.finance.service import clearing_fx
from app.modules.finance.service.clearing_fx import ClearedItem, set_fx_line_currency

__all__ = [
    "build_payment_lines",
    "require_bank_account",
    "set_fx_line_currency",
    "validated_clearing",
]


async def require_bank_account(
    session: AsyncSession, tenant_id: uuid.UUID, account_id: uuid.UUID
) -> Account:
    return await clearing_fx.require_bank_account(
        session, tenant_id, account_id, code="finance.ap_bank_account_not_found"
    )


async def validated_clearing(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    partner_id: uuid.UUID,
    currency_code: str,
    allocations: list[PaymentAllocationCreate],
) -> list[tuple[VendorBill, Decimal]]:
    """Validate every allocation clears an OPEN bill of this partner + currency, by no more than the
    bill's open amount, and return the (bill, allocated) pairs (PLAN 4.5). Clear 422/409."""
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
    """Adapt the validated (bill, amount) pairs into shared ``ClearedItem`` tuples and build the
    balanced payment journal lines + explicit functional amounts via the shared FX helper (D-019).
    AP clears by DEBITING the AP control (Dr AP / Cr bank); each bill's frozen functional is read
    from the CREDIT side of its posting line."""
    items: list[ClearedItem] = []
    for bill, amount in pairs:
        frozen = await clearing_fx.frozen_functional_on_line(
            session,
            tenant_id,
            bill.journal_entry_id,
            bill.ap_account_id,
            Decimal(str(bill.gross_amount)),
            side="credit",
        )
        items.append(
            ClearedItem(
                control_account_id=bill.ap_account_id,
                gross=Decimal(str(bill.gross_amount)),
                cleared=amount,
                frozen_functional=frozen,
            )
        )
    return await clearing_fx.build_clearing_lines(
        session,
        tenant_id,
        items,
        currency_code=currency_code,
        bank_account_id=bank_account_id,
        bank_amount=payment_amount,
        clearing_date=payment_date,
        partner_id=pairs[0][0].partner_id,
        control_is_debit=True,
        control_description="AP clearing",
        bank_description="Bank payment",
    )
