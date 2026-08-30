"""Applying a customer receipt's unapplied (on-account) balance to open invoices (PLAN 20.4, D-084).

The second half of the deposit widening. ``customer_receipts.py`` books cash that clears nothing to
the ``customer_advances`` control; this file spends that balance: it validates the target invoices
with the SAME ``validated_clearing`` a direct allocation uses (open, this partner, this currency,
not over the open amount), refuses to apply more than is unapplied, and posts the reclass through
the SAME ``clearing_fx`` builder — Dr advance control at the rate the deposit was booked at, Cr AR
control at each invoice's frozen rate, the difference realized (D-019). Only the account carrying
the debit differs from an ordinary receipt: the advance control instead of the bank, because no
cash moves at application time.

Nothing here re-derives a total: the receipt's ``unapplied_amount`` and each invoice's
``open_amount`` are balances that only ever get drawn down, and the journal remains the single
financial source of truth for what the advance control holds.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ValidationFailedError
from app.core.money import currency_decimals, quantize_money
from app.modules.finance.constants import (
    AR_PARTNER_TYPE,
    AR_RECEIPT_RECEIPTS_LINK,
    CUSTOMER_ADVANCES,
    DocumentType,
    InvoiceStatus,
)
from app.modules.finance.models import (
    CustomerInvoice,
    CustomerReceipt,
    CustomerReceiptAllocation,
)
from app.modules.finance.receivables_schemas import ReceiptAllocationCreate
from app.modules.finance.schemas import JournalEntryCreate
from app.modules.finance.service import clearing_fx
from app.modules.finance.service.journal import create_draft_entry, post_entry
from app.modules.finance.service.posting_defaults import get_posting_default
from app.modules.finance.service.receipt_clearing import (
    build_receipt_lines,
    validated_clearing,
)
from app.modules.finance.service.receipts_read import get_customer_receipt, get_receipt_allocations


async def apply_receipt(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    receipt_id: uuid.UUID,
    allocations: list[ReceiptAllocationCreate],
    *,
    application_date: date | None = None,
) -> CustomerReceipt:
    """Apply part or all of a receipt's unapplied balance to open invoices (PLAN 20.4, D-084).

    Posts ONE reclass entry (Dr advance control / Cr AR control + realized FX), reduces the
    receipt's ``unapplied_amount``, draws down each invoice's ``open_amount`` and flips its status,
    writes/extends the allocation rows and links receipt->invoice in the doc flow. Caller commits;
    the HTTP layer wraps it in ``run_in_uow`` under an idempotency key (D-013), since it is a
    financial-document effect.

    ``application_date`` is the posting date of the reclass entry (a hospitality caller passes its
    business date); it defaults to the receipt's own date. The FX rate for the advance leg is always
    the RECEIPT date's, whatever the posting date, because that is the rate the liability was booked
    at — anything else would leave a residue on the control account that never clears.
    """
    receipt = await get_customer_receipt(session, tenant_id, receipt_id)
    if not allocations:
        raise ValidationFailedError(
            message="An application must clear at least one invoice",
            code="finance.receipt_no_allocations",
        )
    pairs = await validated_clearing(
        session, tenant_id, receipt.partner_id, receipt.currency_code, allocations
    )
    applied_total = sum((amount for _, amount in pairs), Decimal(0))
    unapplied = quantize_money(
        Decimal(str(receipt.unapplied_amount)), currency_decimals(receipt.currency_code)
    )
    if applied_total > unapplied:
        raise ValidationFailedError(
            message="An application cannot exceed the receipt's unapplied amount",
            code="finance.receipt_apply_exceeds_unapplied",
            details={"unapplied_amount": str(unapplied), "applied": str(applied_total)},
        )

    # The receipt keeps pointing at the entry that RECEIVED the cash (D-017: a posted entry is
    # immutable, so the reclass is its own entry, reachable through the doc flow).
    entry_document_id = await _post_reclass(
        session, tenant_id, receipt, pairs, applied_total, application_date
    )
    receipt.unapplied_amount = unapplied - applied_total
    await _record_application(session, tenant_id, receipt, pairs, entry_document_id)
    await session.flush()
    return receipt


async def _post_reclass(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    receipt: CustomerReceipt,
    pairs: list[tuple[CustomerInvoice, Decimal]],
    applied_total: Decimal,
    application_date: date | None,
) -> uuid.UUID:
    """Build + post the reclass entry and return its DOCUMENT id (for the doc-flow link).

    The advance control takes the side the bank takes on a direct receipt, so the clearing builder
    is called verbatim with the advance account in the bank slot — same frozen-rate reads, same
    realized-FX line, same balance rules. The debit is partner-stamped for the same reason the
    original credit was: the control is pooled per tenant, not per guest.
    """
    advance_account_id = await get_posting_default(session, tenant_id, CUSTOMER_ADVANCES)
    lines, functional_amounts = await build_receipt_lines(
        session,
        tenant_id,
        pairs,
        currency_code=receipt.currency_code,
        bank_account_id=advance_account_id,
        receipt_amount=applied_total,
        receipt_date=receipt.receipt_date,
        bank_description="Customer advance applied",
    )
    for line in lines:
        if line.account_id == advance_account_id:
            line.partner_type = AR_PARTNER_TYPE
            line.partner_id = receipt.partner_id
    entry = await create_draft_entry(
        session,
        tenant_id,
        JournalEntryCreate(
            posting_date=application_date or receipt.receipt_date,
            currency_code=receipt.currency_code,
            description=f"Advance applied {receipt.partner_name}",
            document_type=DocumentType.PAYMENT,
            lines=lines,
        ),
        functional_amounts=functional_amounts,
    )
    await clearing_fx.set_fx_line_currency(session, tenant_id, entry.id)
    await post_entry(session, tenant_id, entry.id, skip_translation=True)
    return entry.document_id


async def _record_application(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    receipt: CustomerReceipt,
    pairs: list[tuple[CustomerInvoice, Decimal]],
    entry_document_id: uuid.UUID,
) -> None:
    """Draw down each invoice, record the allocation and link the documents.

    An allocation row is UNIQUE per (receipt, invoice), so a second application to an invoice this
    receipt already cleared ADDS to the existing row rather than inserting a duplicate — and its
    docflow edge (also unique per pair) is written only the first time.
    """
    existing = {
        allocation.customer_invoice_id: allocation
        for allocation in await get_receipt_allocations(session, tenant_id, receipt.id)
    }
    await docflow.link_documents(
        session,
        tenant_id,
        predecessor=receipt.document_id,
        successor=entry_document_id,
        link_type="posts",
    )
    for invoice, amount in pairs:
        invoice.open_amount = Decimal(str(invoice.open_amount)) - amount
        invoice.status = (
            InvoiceStatus.PAID.value
            if Decimal(str(invoice.open_amount)) == 0
            else InvoiceStatus.PARTIALLY_PAID.value
        )
        allocation = existing.get(invoice.id)
        if allocation is None:
            session.add(
                CustomerReceiptAllocation(
                    tenant_id=tenant_id,
                    receipt_id=receipt.id,
                    customer_invoice_id=invoice.id,
                    allocated_amount=amount,
                )
            )
            await docflow.link_documents(
                session,
                tenant_id,
                predecessor=receipt.document_id,
                successor=invoice.document_id,
                link_type=AR_RECEIPT_RECEIPTS_LINK,
            )
        else:
            allocation.allocated_amount = Decimal(str(allocation.allocated_amount)) + amount
