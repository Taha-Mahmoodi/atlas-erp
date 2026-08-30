"""AR clearing validation + journal-line construction (PLAN 4.6 / 20.4, D-019, D-084).

The three builders both AR money paths share, split out of ``customer_receipts.py`` at the
STRUCTURE §8.4 cap: ``validated_clearing`` (every rule an allocation must satisfy),
``build_receipt_lines`` (the Cr AR control / Dr cash-side clearing lines + realized FX, through the
AP-shared ``clearing_fx`` helper) and ``advance_credit`` (the Cr advance-control line an unapplied
receipt carries).

``customer_receipts.create_and_post_receipt`` uses all three to receive cash;
``receipt_advances.apply_receipt`` uses the first two to spend an advance later, with the advance
control standing in the bank's slot. Keeping them here is what makes "an application obeys exactly
the rules a direct allocation does" a shared implementation rather than a claim.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.money import currency_decimals, quantize_money
from app.modules.finance.constants import (
    AR_PARTNER_TYPE,
    CUSTOMER_ADVANCES,
    InvoiceStatus,
    RateKind,
)
from app.modules.finance.models import CustomerInvoice
from app.modules.finance.receivables_schemas import ReceiptAllocationCreate
from app.modules.finance.schemas import JournalLineCreate
from app.modules.finance.service import clearing_fx, fx
from app.modules.finance.service.clearing_fx import ClearedItem
from app.modules.finance.service.posting_defaults import get_posting_default


async def validated_clearing(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    partner_id: uuid.UUID,
    currency_code: str,
    allocations: list[ReceiptAllocationCreate],
) -> list[tuple[CustomerInvoice, Decimal]]:
    """Validate every allocation clears an OPEN invoice of this partner + currency, by no more than
    the invoice's open amount; return the (invoice, allocated) pairs (PLAN 4.6). Clear 422/409.

    An EMPTY list is valid here since PLAN 20.4 — an unapplied receipt clears nothing — so the
    "must clear something" rule belongs to the caller that needs it (``apply_receipt``), not to the
    per-allocation validation every applied allocation still passes unchanged. Shared with
    ``receipt_advances`` so an application obeys exactly the rules a direct allocation does."""
    pairs: list[tuple[CustomerInvoice, Decimal]] = []
    for alloc in allocations:
        invoice = await session.get(CustomerInvoice, alloc.invoice_id)
        if invoice is None or invoice.tenant_id != tenant_id:
            raise ValidationFailedError(
                message="A receipt allocation references an unknown invoice",
                code="finance.customer_invoice_not_found",
                details={"invoice_id": str(alloc.invoice_id)},
            )
        if invoice.status not in (
            InvoiceStatus.POSTED.value,
            InvoiceStatus.PARTIALLY_PAID.value,
        ):
            raise ConflictError(
                message="Only a posted, open invoice can be received",
                code="finance.invoice_not_open",
                details={"invoice_id": str(invoice.id), "status": invoice.status},
            )
        if invoice.partner_id != partner_id:
            raise ValidationFailedError(
                message="All invoices in a receipt must belong to the same partner",
                code="finance.receipt_partner_mismatch",
                details={"invoice_id": str(invoice.id)},
            )
        if invoice.currency_code != currency_code:
            raise ValidationFailedError(
                message="All invoices in a receipt must share the receipt currency",
                code="finance.receipt_currency_mismatch",
                details={"invoice_id": str(invoice.id), "currency_code": invoice.currency_code},
            )
        amount = quantize_money(alloc.amount, currency_decimals(currency_code))
        if amount <= 0:
            raise ValidationFailedError(
                message="An allocation amount must be positive",
                code="finance.receipt_allocation_not_positive",
                details={"invoice_id": str(invoice.id)},
            )
        if amount > Decimal(str(invoice.open_amount)):
            raise ValidationFailedError(
                message="An allocation cannot exceed the invoice's open amount",
                code="finance.receipt_overallocated",
                details={"invoice_id": str(invoice.id), "open_amount": str(invoice.open_amount)},
            )
        pairs.append((invoice, amount))
    return pairs


async def build_receipt_lines(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    pairs: list[tuple[CustomerInvoice, Decimal]],
    *,
    currency_code: str,
    bank_account_id: uuid.UUID,
    receipt_amount: Decimal,
    receipt_date: date,
    bank_description: str = "Bank receipt",
) -> tuple[list, list[tuple[Decimal, Decimal]]]:
    """Adapt the validated (invoice, amount) pairs into shared ``ClearedItem`` tuples and build the
    balanced receipt journal lines + explicit functional amounts via the shared FX helper (D-019).
    AR clears by CREDITING the AR control (Cr AR / Dr bank); each invoice's frozen functional is
    read from the DEBIT side of its posting line."""
    items: list[ClearedItem] = []
    for invoice, amount in pairs:
        frozen = await clearing_fx.frozen_functional_on_line(
            session,
            tenant_id,
            invoice.journal_entry_id,
            invoice.ar_account_id,
            Decimal(str(invoice.gross_amount)),
            side="debit",
        )
        items.append(
            ClearedItem(
                control_account_id=invoice.ar_account_id,
                gross=Decimal(str(invoice.gross_amount)),
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
        bank_amount=receipt_amount,
        clearing_date=receipt_date,
        partner_id=pairs[0][0].partner_id,
        control_is_debit=False,
        control_description="AR clearing",
        bank_description=bank_description,
    )


async def advance_credit(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    unapplied: Decimal,
    *,
    currency_code: str,
    partner_id: uuid.UUID,
    receipt_date: date,
) -> tuple[JournalLineCreate, tuple[Decimal, Decimal]]:
    """The Cr advance-control line for the part of a receipt that clears nothing (PLAN 20.4,
    D-084), plus its explicit functional (debit, credit) pair.

    The account is the ``customer_advances`` posting default — the D-019 data-driven wiring, so a
    tenant that never mapped it fails loud (422) instead of guessing a liability account. The line
    carries partner_type + partner_id because the control is POOLED: an anonymous credit is a
    deposit no one can find again. Valued at the receipt-date rate, exactly like the cash it arrived
    as, so the deposit leg carries no realized FX — the FX becomes real only when ``apply_receipt``
    clears it against an invoice frozen at a different rate."""
    account_id = await get_posting_default(session, tenant_id, CUSTOMER_ADVANCES)
    func_code = await fx.functional_currency_or_none(session, tenant_id)
    if func_code is None or func_code == currency_code:
        functional = unapplied
    else:
        rate = await fx.get_rate(
            session, tenant_id, currency_code, func_code, receipt_date, RateKind.SPOT
        )
        functional = quantize_money(unapplied * rate, currency_decimals(func_code))
    line = JournalLineCreate(
        account_id=account_id,
        description="Customer advance",
        transaction_credit_amount=unapplied,
        partner_type=AR_PARTNER_TYPE,
        partner_id=partner_id,
    )
    return line, (Decimal(0), functional)
