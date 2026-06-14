"""Procurement invoice-match → AP vendor-bill handler (PLAN 6.4, D-042).

``create_bill_for_match`` subscribes to ``procurement.invoice_match.matched`` and creates + posts
the AP vendor bill (Dr GR/IR at PO cost + Dr/Cr purchase-price-variance for the in-tolerance price
difference + Dr input tax / Cr AP control at the vendor-invoiced total) in the SAME transaction as
the match post. Procurement PUBLISHES the event; finance handles its OWN bill posting (procurement
must not import finance/service — STRUCTURE §5). The bill DEBITS GR/IR at exactly the cost the goods
receipt CREDITED it at receipt, so the GR/IR clearing account nets to zero — the procure-to-pay loop
closes. A closed invoice period trips the bill's journal period trigger here and rolls the whole
match post back. The bill is posted through the finance AP service (never raw inserts) so every
AP/journal invariant fires.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.modules.finance.payables_schemas import VendorBillCreate, VendorBillLineCreate
from app.modules.finance.service.vendor_bills import create_vendor_bill, post_vendor_bill
from app.modules.procurement.constants import INVOICE_MATCH_BILLED_BY_BILL_LINK
from app.modules.procurement.events import InvoiceMatched


async def create_bill_for_match(session: AsyncSession, event: InvoiceMatched) -> None:
    """Create + post the AP vendor bill for a posted 3-way match (PLAN 6.4, D-042), in the match's
    transaction.

    Builds a draft vendor bill whose lines DEBIT GR/IR at PO cost and route the in-tolerance price
    difference to the purchase-price-variance account, with the header tax code driving input tax,
    then posts it through the finance AP service (``create_vendor_bill`` + ``post_vendor_bill``) so
    every AP/journal invariant fires exactly as for a hand-entered bill. The AP control is credited
    at the vendor-invoiced gross, partner-keyed by the opaque vendor id (D-029); the bill's due date
    is invoice_date + the vendor's terms (procurement computed it). The GR/IR debit equals the GR/IR
    credit at receipt, so GR/IR nets to zero — the procure-to-pay loop closes. Linking the match
    document to the bill document ('billed_by') completes the PO → GR → match → bill docflow chain.

    Registered via ``app.main.register_event_handlers`` (the deterministic D-011 seam), so the test
    harness re-registers it after its per-test ``clear_subscriptions`` reset (D-025)."""
    lines: list[VendorBillLineCreate] = []
    for line in event.lines:
        # The GR/IR clearing portion at PO cost (taxable): Dr GR/IR, clearing the receipt credit.
        lines.append(
            VendorBillLineCreate(
                account_id=event.gr_ir_account_id,
                description="GR/IR clearing",
                net_amount=line.gr_ir_amount,
                tax_code_id=event.tax_code_id,
            )
        )
        # The price variance (taxable, same code so input tax matches the full invoice): Dr/Cr PPV.
        # Dropped when zero so a clean match posts no PPV line.
        if line.price_variance != 0:
            lines.append(
                VendorBillLineCreate(
                    account_id=event.ppv_account_id,
                    description="Purchase price variance",
                    net_amount=line.price_variance,
                    tax_code_id=event.tax_code_id,
                )
            )

    bill = await create_vendor_bill(
        session,
        event.tenant_id,
        VendorBillCreate(
            partner_id=event.partner_id,
            partner_name=event.partner_name,
            bill_date=event.invoice_date,
            due_date=event.due_date,
            currency_code=event.currency_code,
            ap_account_id=event.ap_account_id,
            bill_external_ref=event.vendor_invoice_ref,
            description=f"3-way match {event.match_number}",
            lines=lines,
        ),
    )
    await post_vendor_bill(session, event.tenant_id, bill.id, posting_date=event.invoice_date)
    await docflow.link_documents(
        session,
        event.tenant_id,
        predecessor=event.document_id,
        successor=bill.document_id,
        link_type=INVOICE_MATCH_BILLED_BY_BILL_LINK,
    )
