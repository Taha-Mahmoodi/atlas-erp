"""Sales billing → AR customer-invoice + sales return → AR credit-note handlers (PLAN 7.4, D-046).

``create_invoice_for_billing`` subscribes to a posted sales billing and creates + posts the AR
customer invoice (the MIRROR of ``create_bill_for_match``, sign-flipped: Dr AR control gross / Cr
revenue net / Cr output tax). ``create_credit_note_for_return`` subscribes to a posted sales return
and creates + posts the AR credit note (the sign-flipped invoice: Dr revenue / Dr output tax / Cr AR
control), reducing what the customer owes. Sales PUBLISHES; finance handles its OWN posting (sales
must not import finance/service — STRUCTURE §5), both in the SAME transaction as the triggering post
so a closed period rolls the whole sales post back. Posted through the finance AR service (never raw
inserts) so every AR/journal invariant fires.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.modules.finance.receivables_schemas import (
    CustomerCreditNoteCreate,
    CustomerInvoiceCreate,
    CustomerInvoiceLineCreate,
)
from app.modules.finance.service.credit_notes import create_and_post_customer_credit_note
from app.modules.finance.service.customer_invoices import (
    create_customer_invoice,
    post_customer_invoice,
)
from app.modules.sales.constants import (
    BILLING_INVOICED_BY_INVOICE_LINK,
    RETURN_CREDITED_BY_CREDIT_NOTE_LINK,
)
from app.modules.sales.events import BillingInvoiced, ReturnCredited


async def create_invoice_for_billing(session: AsyncSession, event: BillingInvoiced) -> None:
    """Create + post the AR customer invoice for a posted sales billing (PLAN 7.4, D-046), in the
    billing's transaction — the MIRROR of ``create_bill_for_match`` (match → AP bill), sign-flipped.

    Builds a draft customer invoice whose lines CREDIT the sales-revenue account at each net (the
    header tax code drives output tax), then posts it through the finance AR service
    (``create_customer_invoice`` + ``post_customer_invoice``) so every AR/journal invariant fires
    exactly as for a hand-entered invoice: Dr AR control gross / Cr revenue net / Cr output tax,
    partner-keyed by the opaque customer id (D-029), due = billing_date + the terms sales computed.
    Linking the billing document to the invoice document ('invoiced_by_invoice') completes the
    order → delivery → billing → invoice docflow chain. A closed billing period trips the invoice's
    journal trigger here and rolls the whole billing post back.

    Registered via ``app.main.register_event_handlers`` (the deterministic D-011 seam), so the test
    harness re-registers it after its per-test ``clear_subscriptions`` reset (D-025)."""
    lines = [
        CustomerInvoiceLineCreate(
            account_id=event.revenue_account_id,
            description="Sales revenue",
            net_amount=line.net_amount,
            tax_code_id=line.tax_code_id,
        )
        for line in event.lines
    ]
    invoice = await create_customer_invoice(
        session,
        event.tenant_id,
        CustomerInvoiceCreate(
            partner_id=event.partner_id,
            partner_name=event.partner_name,
            invoice_date=event.billing_date,
            due_date=event.due_date,
            currency_code=event.currency_code,
            ar_account_id=event.ar_account_id,
            external_ref=event.billing_number,
            description=f"Sales billing {event.billing_number}",
            lines=lines,
        ),
    )
    await post_customer_invoice(
        session, event.tenant_id, invoice.id, posting_date=event.billing_date
    )
    await docflow.link_documents(
        session,
        event.tenant_id,
        predecessor=event.document_id,
        successor=invoice.document_id,
        link_type=BILLING_INVOICED_BY_INVOICE_LINK,
    )


async def create_credit_note_for_return(session: AsyncSession, event: ReturnCredited) -> None:
    """Create + post the AR credit note for a posted sales return (PLAN 7.4, D-046), in the return's
    transaction. Builds a credit note (the sign-flipped customer invoice) whose lines DEBIT
    sales-revenue at each net (reversing revenue) and whose AR control is CREDITED at the gross
    (reversing AR), the header tax code reversing output tax — posted via
    ``create_and_post_customer_credit_note`` so every journal invariant fires. Links the return
    document → 'credited_by' → credit-note document. A closed return period trips the journal
    trigger here and rolls the whole return post back. Registered via the D-011 seam."""
    lines = [
        CustomerInvoiceLineCreate(
            account_id=event.revenue_account_id,
            description="Sales revenue reversal",
            net_amount=line.net_amount,
            tax_code_id=line.tax_code_id,
        )
        for line in event.lines
    ]
    note = await create_and_post_customer_credit_note(
        session,
        event.tenant_id,
        CustomerCreditNoteCreate(
            partner_id=event.partner_id,
            partner_name=event.partner_name,
            credit_note_date=event.credit_note_date,
            currency_code=event.currency_code,
            ar_account_id=event.ar_account_id,
            external_ref=event.return_number,
            description=f"Sales return {event.return_number}",
            lines=lines,
        ),
        posting_date=event.credit_note_date,
    )
    await docflow.link_documents(
        session,
        event.tenant_id,
        predecessor=event.document_id,
        successor=note.document_id,
        link_type=RETURN_CREDITED_BY_CREDIT_NOTE_LINK,
    )
