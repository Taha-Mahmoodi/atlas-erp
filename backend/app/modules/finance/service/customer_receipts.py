"""Customer receipt posting + open-item clearing (PLAN 4.6, AR — D-019 realized FX at clearing).

The AP ``vendor_payments.py`` mirror with the sign flipped: a receipt CREDITS the AR control for the
sum cleared and DEBITS the bank for the cash received (vs AP's Dr AP / Cr bank). ``create_and_post_
receipt`` validates the cleared invoices (right partner, currency, open, not over-allocated), builds
the balanced clearing entry with explicit functional amounts via the SHARED ``clearing_fx`` helper
(Cr AR at each invoice's frozen rate, Dr bank at the receipt rate, + a realized-FX line so it
balances), posts it with ``skip_translation``, claims the gapless receipt number (D-012), reduces
each invoice's open_amount and flips its status, records the allocations, links receipt->invoices
(docflow 'receipts'), and publishes ``CustomerReceiptPosted``.

A receipt may also arrive with NOTHING to clear, or with more cash than it clears (PLAN 20.4,
D-084): ``amount`` must be >= the allocation sum, and the excess becomes ``unapplied_amount``,
credited to the ``customer_advances`` control account with partner_type/partner_id stamped so the
pooled liability reconciles per customer. ``receipt_advances.apply_receipt`` spends that balance
later. Allocating MORE than was received stays refused (#73 with the sign flipped: the difference
would otherwise flow into the realized-FX line as a phantom gain).

Finance stays the bottom dependency; partner ids stay opaque (D-029). The clearing/FX math is shared
with AP (``clearing_fx.py``); the AR aging projection lives in ``ar_aging.py``, the reads in
``receipts_read.py``, the validation + line builders in ``receipt_clearing.py`` and the on-account
application in ``receipt_advances.py`` (all split out to keep every file under the STRUCTURE §3
cap).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.events import publish
from app.core.exceptions import ValidationFailedError
from app.core.money import currency_decimals, quantize_money
from app.core.numbering import claim_number, ensure_sequence
from app.modules.finance.constants import (
    AR_RECEIPT_DOC_TYPE,
    AR_RECEIPT_NUMBER_PADDING,
    AR_RECEIPT_NUMBER_PREFIX,
    AR_RECEIPT_RECEIPTS_LINK,
    AR_RECEIPT_SEQUENCE_NAME,
    DocumentType,
    InvoiceStatus,
    ReceiptStatus,
)
from app.modules.finance.events import CustomerReceiptPosted
from app.modules.finance.models import (
    CustomerInvoice,
    CustomerReceipt,
    CustomerReceiptAllocation,
)
from app.modules.finance.receivables_schemas import CustomerReceiptCreate
from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate
from app.modules.finance.service import clearing_fx
from app.modules.finance.service.journal import create_draft_entry, post_entry
from app.modules.finance.service.receipt_clearing import (
    advance_credit,
    build_receipt_lines,
    validated_clearing,
)


async def create_and_post_receipt(
    session: AsyncSession, tenant_id: uuid.UUID, payload: CustomerReceiptCreate
) -> CustomerReceipt:
    """Create + post a customer receipt clearing one or more open invoices (PLAN 4.6, D-019).

    Validates the invoices are open, same partner, same currency, none over-allocated; builds the
    balanced clearing entry (Cr AR, Dr bank, + realized FX), posts it with explicit functional
    amounts (skip_translation), claims the gapless receipt number, reduces each invoice's
    open_amount and flips its status (PARTIALLY_PAID/PAID), records allocations, links
    receipt->invoices (docflow 'receipts'), and publishes ``CustomerReceiptPosted``. Caller commits.

    ``allocations`` may be empty and ``amount`` may EXCEED their sum (PLAN 20.4, D-084): the excess
    is the receipt's ``unapplied_amount``, credited to the ``customer_advances`` control on a
    partner-stamped line inside the same entry. Only the reverse — allocating more than was
    received — is refused.
    """
    await clearing_fx.require_bank_account(
        session, tenant_id, payload.bank_account_id, code="finance.ar_bank_account_not_found"
    )
    pairs = await validated_clearing(
        session, tenant_id, payload.partner_id, payload.currency_code, payload.allocations
    )
    receipt_amount = quantize_money(payload.amount, currency_decimals(payload.currency_code))
    allocated_total = sum((amount for _, amount in pairs), Decimal(0))
    if receipt_amount < allocated_total:
        # #73: without this, the difference flows into the realized-FX line and a plain
        # same-currency under-payment is misbooked as a phantom FX gain/loss. The OTHER direction
        # (more cash than allocations) is the D-084 unapplied balance below, not an error.
        raise ValidationFailedError(
            message="The receipt amount cannot be less than the sum of its allocations",
            code="finance.receipt_allocation_sum_mismatch",
            details={"amount": str(receipt_amount), "allocated": str(allocated_total)},
        )
    unapplied = receipt_amount - allocated_total

    lines: list[JournalLineCreate] = []
    functional_amounts: list[tuple[Decimal, Decimal]] = []
    if pairs:
        lines, functional_amounts = await build_receipt_lines(
            session,
            tenant_id,
            pairs,
            currency_code=payload.currency_code,
            bank_account_id=payload.bank_account_id,
            receipt_amount=allocated_total,
            receipt_date=payload.receipt_date,
        )
    if unapplied > 0:
        advance_line, advance_functional = await advance_credit(
            session,
            tenant_id,
            unapplied,
            currency_code=payload.currency_code,
            partner_id=payload.partner_id,
            receipt_date=payload.receipt_date,
        )
        if pairs:
            # ONE cash movement, one bank line: the clearing builder debited the bank for the
            # allocated part only, so grow that line to the full amount received rather than
            # posting a second debit to the same account.
            index = next(
                i for i, line in enumerate(lines) if line.account_id == payload.bank_account_id
            )
            lines[index].transaction_debit_amount = receipt_amount
            functional_amounts[index] = (
                functional_amounts[index][0] + advance_functional[1],
                Decimal(0),
            )
        else:
            lines.append(
                JournalLineCreate(
                    account_id=payload.bank_account_id,
                    description="Bank receipt",
                    transaction_debit_amount=receipt_amount,
                )
            )
            functional_amounts.append((advance_functional[1], Decimal(0)))
        lines.append(advance_line)
        functional_amounts.append(advance_functional)

    entry = await create_draft_entry(
        session,
        tenant_id,
        JournalEntryCreate(
            posting_date=payload.receipt_date,
            currency_code=payload.currency_code,
            description=f"Customer receipt {payload.partner_name}",
            document_type=DocumentType.PAYMENT,
            lines=lines,
        ),
        functional_amounts=functional_amounts,
    )
    await clearing_fx.set_fx_line_currency(session, tenant_id, entry.id)
    await post_entry(session, tenant_id, entry.id, skip_translation=True)

    receipt = await _record_receipt(
        session, tenant_id, payload, receipt_amount, unapplied, pairs, entry.id, entry.document_id
    )
    return receipt


async def _record_receipt(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    payload: CustomerReceiptCreate,
    receipt_amount: Decimal,
    unapplied: Decimal,
    pairs: list[tuple[CustomerInvoice, Decimal]],
    journal_entry_id: uuid.UUID,
    journal_document_id: uuid.UUID,
) -> CustomerReceipt:
    """Persist the receipt document + allocations after its journal posted (PLAN 4.6): register the
    document, claim the number, reduce each cleared invoice's open_amount + flip its status, write
    the allocations, link receipt->invoices, and publish the event. ``pairs`` are the
    (invoice, amount) pairs already validated before the journal posted."""
    receipt_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        AR_RECEIPT_DOC_TYPE,
        receipt_id,
        doc_number=None,
        status=ReceiptStatus.POSTED.value,
    )
    await ensure_sequence(
        session,
        tenant_id,
        AR_RECEIPT_SEQUENCE_NAME,
        AR_RECEIPT_NUMBER_PREFIX,
        AR_RECEIPT_NUMBER_PADDING,
        year_reset=True,
    )
    receipt_number = await claim_number(
        session, tenant_id, AR_RECEIPT_SEQUENCE_NAME, on_date=payload.receipt_date
    )
    receipt = CustomerReceipt(
        id=receipt_id,
        tenant_id=tenant_id,
        document_id=document.id,
        partner_id=payload.partner_id,
        partner_name=payload.partner_name,
        receipt_number=receipt_number,
        receipt_date=payload.receipt_date,
        currency_code=payload.currency_code,
        bank_account_id=payload.bank_account_id,
        amount=receipt_amount,
        unapplied_amount=unapplied,
        journal_entry_id=journal_entry_id,
        status=ReceiptStatus.POSTED.value,
        description=payload.description,
    )
    session.add(receipt)

    cleared_invoice_ids: list[uuid.UUID] = []
    for invoice, amount in pairs:
        invoice.open_amount = Decimal(str(invoice.open_amount)) - amount
        invoice.status = (
            InvoiceStatus.PAID.value
            if Decimal(str(invoice.open_amount)) == 0
            else InvoiceStatus.PARTIALLY_PAID.value
        )
        session.add(
            CustomerReceiptAllocation(
                tenant_id=tenant_id,
                receipt_id=receipt_id,
                customer_invoice_id=invoice.id,
                allocated_amount=amount,
            )
        )
        cleared_invoice_ids.append(invoice.id)
    await session.flush()

    await docflow.set_document_status(
        session,
        tenant_id,
        receipt.document_id,
        status=ReceiptStatus.POSTED.value,
        doc_number=receipt_number,
    )
    # The journal entry was created INSIDE the receipt flow, so wire its docflow link to the receipt
    # as well (receipt 'posts' its clearing journal entry, mirroring an invoice->journal link).
    await docflow.link_documents(
        session,
        tenant_id,
        predecessor=receipt.document_id,
        successor=journal_document_id,
        link_type="posts",
    )
    for invoice, _amount in pairs:
        await docflow.link_documents(
            session,
            tenant_id,
            predecessor=receipt.document_id,
            successor=invoice.document_id,
            link_type=AR_RECEIPT_RECEIPTS_LINK,
        )

    publish(
        session,
        CustomerReceiptPosted(
            tenant_id=tenant_id,
            receipt_id=receipt.id,
            receipt_number=receipt_number,
            journal_entry_id=journal_entry_id,
            partner_id=receipt.partner_id,
            currency_code=receipt.currency_code,
            amount=receipt_amount,
            cleared_invoice_ids=tuple(cleared_invoice_ids),
        ),
    )
    return receipt
