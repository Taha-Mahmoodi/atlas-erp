"""Customer receipt posting + open-item clearing (PLAN 4.6, AR — D-019 realized FX at clearing).

The AP ``vendor_payments.py`` mirror with the sign flipped: a receipt CREDITS the AR control for the
sum cleared and DEBITS the bank for the cash received (vs AP's Dr AP / Cr bank). ``create_and_post_
receipt`` validates the cleared invoices (right partner, currency, open, not over-allocated), builds
the balanced clearing entry with explicit functional amounts via the SHARED ``clearing_fx`` helper
(Cr AR at each invoice's frozen rate, Dr bank at the receipt rate, + a realized-FX line so it
balances), posts it with ``skip_translation``, claims the gapless receipt number (D-012), reduces
each invoice's open_amount and flips its status, records the allocations, links receipt->invoices
(docflow 'receipts'), and publishes ``CustomerReceiptPosted``.

Finance stays the bottom dependency; partner ids stay opaque (D-029). The clearing/FX math is shared
with AP (``clearing_fx.py``); the AR aging projection lives in ``ar_aging.py`` (both split out to
keep every file under the STRUCTURE §3 cap).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.events import publish
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
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
from app.modules.finance.receivables_schemas import (
    CustomerReceiptCreate,
    ReceiptAllocationCreate,
)
from app.modules.finance.schemas import JournalEntryCreate
from app.modules.finance.service import clearing_fx
from app.modules.finance.service.clearing_fx import ClearedItem
from app.modules.finance.service.journal import create_draft_entry, post_entry


async def _validated_clearing(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    partner_id: uuid.UUID,
    currency_code: str,
    allocations: list[ReceiptAllocationCreate],
) -> list[tuple[CustomerInvoice, Decimal]]:
    """Validate every allocation clears an OPEN invoice of this partner + currency, by no more than
    the invoice's open amount; return the (invoice, allocated) pairs (PLAN 4.6). Clear 422/409."""
    if not allocations:
        raise ValidationFailedError(
            message="A receipt must clear at least one invoice",
            code="finance.receipt_no_allocations",
        )
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


async def _build_receipt_lines(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    pairs: list[tuple[CustomerInvoice, Decimal]],
    *,
    currency_code: str,
    bank_account_id: uuid.UUID,
    receipt_amount: Decimal,
    receipt_date: date,
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
        bank_description="Bank receipt",
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
    """
    await clearing_fx.require_bank_account(
        session, tenant_id, payload.bank_account_id, code="finance.ar_bank_account_not_found"
    )
    pairs = await _validated_clearing(
        session, tenant_id, payload.partner_id, payload.currency_code, payload.allocations
    )
    receipt_amount = quantize_money(payload.amount, currency_decimals(payload.currency_code))
    allocated_total = sum((amount for _, amount in pairs), Decimal(0))
    if receipt_amount != allocated_total:
        # #73: without this, the difference flows into the realized-FX line and a plain
        # same-currency over/under-payment is misbooked as a phantom FX gain/loss.
        raise ValidationFailedError(
            message="The receipt amount must equal the sum of its allocations",
            code="finance.receipt_allocation_sum_mismatch",
            details={"amount": str(receipt_amount), "allocated": str(allocated_total)},
        )

    lines, functional_amounts = await _build_receipt_lines(
        session,
        tenant_id,
        pairs,
        currency_code=payload.currency_code,
        bank_account_id=payload.bank_account_id,
        receipt_amount=receipt_amount,
        receipt_date=payload.receipt_date,
    )

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
        session, tenant_id, payload, receipt_amount, pairs, entry.id, entry.document_id
    )
    return receipt


async def _record_receipt(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    payload: CustomerReceiptCreate,
    receipt_amount: Decimal,
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


async def get_customer_receipt(
    session: AsyncSession, tenant_id: uuid.UUID, receipt_id: uuid.UUID
) -> CustomerReceipt:
    receipt = await session.get(CustomerReceipt, receipt_id)
    if receipt is None or receipt.tenant_id != tenant_id:
        raise NotFoundError(
            message="Customer receipt not found", code="finance.customer_receipt_not_found"
        )
    return receipt


async def get_receipt_allocations(
    session: AsyncSession, tenant_id: uuid.UUID, receipt_id: uuid.UUID
) -> list[CustomerReceiptAllocation]:
    stmt = (
        select(CustomerReceiptAllocation)
        .where(
            CustomerReceiptAllocation.tenant_id == tenant_id,
            CustomerReceiptAllocation.receipt_id == receipt_id,
        )
        .order_by(CustomerReceiptAllocation.created_at)
    )
    return list((await session.execute(stmt)).scalars().all())


async def list_customer_receipts(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cursor: str | None,
    limit: int,
    partner_id: uuid.UUID | None = None,
) -> object:
    """Keyset-paginated receipt list, newest receipt_date first (D-014). ``partner_id`` folds into
    the cursor fingerprint."""
    from app.core.pagination import OrderKey, SortDirection, filter_fingerprint, paginate

    stmt = select(CustomerReceipt).where(CustomerReceipt.tenant_id == tenant_id)
    if partner_id is not None:
        stmt = stmt.where(CustomerReceipt.partner_id == partner_id)
    return await paginate(
        session,
        stmt,
        order_by=[
            OrderKey(CustomerReceipt.receipt_date, SortDirection.DESC),
            OrderKey(CustomerReceipt.created_at, SortDirection.DESC),
        ],
        pk=CustomerReceipt.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(partner_id),
    )
