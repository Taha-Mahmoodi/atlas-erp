"""Customer credit notes: create + post the REVERSING AR journal (PLAN 7.4, sales RMA returns).

Finance shipped no credit-note path in 4.6 (invoices, receipts, dunning, aging only), so this is the
minimal credit-memo entrypoint the sales-return handler calls. A credit note is the SIGN-FLIPPED
customer invoice: it is modeled as a ``CustomerInvoice`` row (reusing the AR table — no new model)
whose POSTED journal carries ``document_type`` AR_CREDIT_NOTE and reverses the invoice's directions:

  invoice  posts  Dr AR control (gross)  / Cr revenue (net) / Cr output tax
  credit   posts  Dr revenue (net) + Dr output tax / Cr AR control (gross)

so the credit note REDUCES what the customer owes (and reverses recognized revenue + output tax).
The
draft build (tax computation + totals) is shared verbatim with ``create_customer_invoice`` — the
only
difference is the journal direction at posting + the CN- number + the AR_CREDIT_NOTE doc type. The
stored ``gross/net/tax`` amounts are positive (a credit note's magnitude); ``open_amount`` stays 0
(a
credit note is not an open receivable to dun — it is a reduction, documented in the constants).

Finance stays the bottom dependency — this module imports no other module. The journal engine
handles
period/numbering/immutability/FX exactly as for an invoice; a closed credit-note period trips the
entry's period trigger and rolls the whole post (and the sales return that triggered it) back.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.numbering import claim_number, ensure_sequence
from app.modules.finance.constants import (
    AR_CREDIT_NOTE_DOC_TYPE,
    AR_CREDIT_NOTE_NUMBER_PADDING,
    AR_CREDIT_NOTE_NUMBER_PREFIX,
    AR_CREDIT_NOTE_POSTS_LINK,
    AR_CREDIT_NOTE_SEQUENCE_NAME,
    AR_PARTNER_TYPE,
    DocumentType,
    InvoiceStatus,
)
from app.modules.finance.models import CustomerInvoice, CustomerInvoiceLine
from app.modules.finance.receivables_schemas import CustomerCreditNoteCreate
from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate
from app.modules.finance.service.customer_invoices import (
    _resolve_tax_accounts,
    create_ar_document_draft,
    get_customer_invoice_lines,
)
from app.modules.finance.service.journal import create_draft_entry, post_entry


def _credit_note_journal_lines(
    note: CustomerInvoice,
    lines: list[CustomerInvoiceLine],
    tax_account_by_code: dict[uuid.UUID, uuid.UUID],
) -> list[JournalLineCreate]:
    """The balanced REVERSING AR journal lines for a credit note (PLAN 7.4): Cr the AR control for
    the gross — partner_id stamped on the AR line so the reduction is partner-keyed (D-029) — Dr
    each
    line's net (reversing the recognized revenue), Dr output tax (reversing the levied tax). The
    EXACT sign-flip of ``customer_invoices._invoice_journal_lines``."""
    journal_lines: list[JournalLineCreate] = [
        JournalLineCreate(
            account_id=note.ar_account_id,
            description=f"AR credit {note.partner_name}",
            transaction_credit_amount=note.gross_amount,
            partner_type=AR_PARTNER_TYPE,
            partner_id=note.partner_id,
        )
    ]
    for line in lines:
        journal_lines.append(
            JournalLineCreate(
                account_id=line.account_id,
                description=line.description,
                transaction_debit_amount=line.net_amount,
                cost_center_id=line.cost_center_id,
                profit_center_id=line.profit_center_id,
                project_id=line.project_id,
            )
        )
        if line.tax_amount and line.tax_code_id is not None:
            journal_lines.append(
                JournalLineCreate(
                    account_id=tax_account_by_code[line.tax_code_id],
                    description="Output tax reversal",
                    transaction_debit_amount=line.tax_amount,
                )
            )
    return journal_lines


async def create_and_post_customer_credit_note(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    payload: CustomerCreditNoteCreate,
    *,
    posting_date: date | None = None,
) -> CustomerInvoice:
    """Create a credit note + post its reversing AR journal in one step (PLAN 7.4). Reuses the AR
    invoice draft builder (so tax + totals match an invoice exactly), then posts the SIGN-FLIPPED
    journal (Dr revenue net + Dr output tax / Cr AR control gross, document_type AR_CREDIT_NOTE),
    claims the gapless CN- number, links the credit-note document to its journal ('posts'), sets
    ``open_amount`` = 0 + status POSTED. ``posting_date`` defaults to the credit-note date. A closed
    period trips the entry's period trigger and rolls the whole post back."""
    # Reuse the shared AR draft build (validates AR + line accounts, computes per-line output tax +
    # totals identically) but register the document under the CREDIT-NOTE doc type — a credit note's
    # magnitude math is the invoice's, only the journal direction (below) and the doc type flip.
    note = await create_ar_document_draft(
        session,
        tenant_id,
        partner_id=payload.partner_id,
        partner_name=payload.partner_name,
        invoice_date=payload.credit_note_date,
        due_date=payload.credit_note_date,
        currency_code=payload.currency_code,
        ar_account_id=payload.ar_account_id,
        external_ref=payload.external_ref,
        description=payload.description,
        lines=payload.lines,
        doc_type=AR_CREDIT_NOTE_DOC_TYPE,
    )

    lines = await get_customer_invoice_lines(session, tenant_id, note.id)
    tax_account_by_code = await _resolve_tax_accounts(session, tenant_id, lines)

    entry = await create_draft_entry(
        session,
        tenant_id,
        JournalEntryCreate(
            posting_date=posting_date or payload.credit_note_date,
            currency_code=note.currency_code,
            description=f"Customer credit note {note.partner_name}",
            document_type=DocumentType.AR_CREDIT_NOTE,
            lines=_credit_note_journal_lines(note, lines, tax_account_by_code),
        ),
    )
    await post_entry(session, tenant_id, entry.id)

    await ensure_sequence(
        session,
        tenant_id,
        AR_CREDIT_NOTE_SEQUENCE_NAME,
        AR_CREDIT_NOTE_NUMBER_PREFIX,
        AR_CREDIT_NOTE_NUMBER_PADDING,
        year_reset=True,
    )
    number = await claim_number(
        session, tenant_id, AR_CREDIT_NOTE_SEQUENCE_NAME, on_date=payload.credit_note_date
    )

    note.invoice_number = number
    note.journal_entry_id = entry.id
    # A credit note is not an open receivable to dun — it reduces what the customer owes, so it
    # carries no open balance (documented in the constants). The reduction is in the journal.
    note.open_amount = 0
    note.status = InvoiceStatus.POSTED.value
    await session.flush()

    await docflow.set_document_status(
        session,
        tenant_id,
        note.document_id,
        status=InvoiceStatus.POSTED.value,
        doc_number=number,
    )
    await docflow.link_documents(
        session,
        tenant_id,
        predecessor=note.document_id,
        successor=entry.document_id,
        link_type=AR_CREDIT_NOTE_POSTS_LINK,
    )
    return note


__all__ = ["create_and_post_customer_credit_note"]
