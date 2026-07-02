"""3-way invoice-match post / override / cancel (PLAN 6.4, D-042), split from ``invoice_matches.py``
at the 400-line cap (the goods_receipts writes/reads precedent). The create path + its validation
helpers + the shared ``po_lines_for`` stay in ``invoice_matches.py``; the state-transition actions
live here. Re-exported with create + reads from the package ``__init__`` as one ``service`` surface.

``post_invoice_match`` is the heart: in ONE transaction it raises each PO line's billed_quantity,
advances the PO toward CLOSED, links docflow PO→match + GR→match, sets the match POSTED, and
PUBLISHES ``InvoiceMatched`` so finance's handler creates + posts the AP vendor bill (Dr GR/IR at PO
cost +
Dr/Cr PPV / Cr AP at the invoiced total), clearing the GR/IR account the goods receipt credited at
receipt — the procure-to-pay loop closes. A closed invoice period trips the bill's journal trigger
and rolls it ALL back.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.events import publish
from app.core.exceptions import ConflictError
from app.core.money import quantize_for_currency
from app.modules.finance import queries as finance_queries
from app.modules.procurement import queries as procurement_queries
from app.modules.procurement.constants import (
    GR_MATCHED_BY_INVOICE_MATCH_LINK,
    PO_MATCHED_BY_INVOICE_MATCH_LINK,
    MatchStatus,
    PurchaseOrderStatus,
)
from app.modules.procurement.events import InvoiceMatchBillLine, InvoiceMatched
from app.modules.procurement.models import (
    GoodsReceiptLine,
    InvoiceMatch,
    InvoiceMatchLine,
    PurchaseOrder,
)
from app.modules.procurement.service.invoice_match_reads import (
    get_invoice_match,
    get_invoice_match_lines,
)
from app.modules.procurement.service.invoice_matches import po_lines_for


async def override_invoice_match(
    session: AsyncSession, tenant_id: uuid.UUID, match_id: uuid.UUID
) -> InvoiceMatch:
    """Clear an EXCEPTION so the match may post (PLAN 6.4 — the invoice-release control). Only an
    EXCEPTION match can be overridden; it moves to MATCHED. An authorized user accepting the price
    difference is recorded via the audited status change (procurement.invoice_match.manage)."""
    match = await get_invoice_match(session, tenant_id, match_id)
    if MatchStatus(match.status) != MatchStatus.EXCEPTION:
        raise ConflictError(
            message="Only a match in EXCEPTION can be overridden",
            code="procurement.match_not_exception",
            details={"status": match.status},
        )
    match.status = MatchStatus.MATCHED.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, match.document_id, status=MatchStatus.MATCHED.value
    )
    return match


async def cancel_invoice_match(
    session: AsyncSession, tenant_id: uuid.UUID, match_id: uuid.UUID
) -> InvoiceMatch:
    """Cancel a DRAFT/MATCHED/EXCEPTION match before posting (PLAN 6.4). A POSTED match is TERMINAL
    — it triggered an AP bill, so it is corrected by a credit memo / reversal (Phase 7), never
    cancelled. Cancelling raises no bill and changes no billed_quantity."""
    match = await get_invoice_match(session, tenant_id, match_id)
    if MatchStatus(match.status) in (MatchStatus.POSTED, MatchStatus.CANCELLED):
        raise ConflictError(
            message=f"A {match.status} invoice match cannot be cancelled",
            code="procurement.match_not_cancellable",
            details={"status": match.status},
        )
    match.status = MatchStatus.CANCELLED.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, match.document_id, status=MatchStatus.CANCELLED.value
    )
    return match


def _require_postable(match: InvoiceMatch, match_id: uuid.UUID) -> None:
    """Only a MATCHED match can post: a POSTED one is terminal, an EXCEPTION must be overridden
    first, any other state is not postable (PLAN 6.4)."""
    status = MatchStatus(match.status)
    if status == MatchStatus.POSTED:
        raise ConflictError(
            message="The invoice match is already posted",
            code="procurement.match_already_posted",
            details={"invoice_match_id": str(match_id)},
        )
    if status == MatchStatus.EXCEPTION:
        raise ConflictError(
            message="A match in EXCEPTION must be overridden before it can be posted",
            code="procurement.match_in_exception",
            details={"invoice_match_id": str(match_id)},
        )
    if status != MatchStatus.MATCHED:
        raise ConflictError(
            message=f"A {match.status} invoice match cannot be posted",
            code="procurement.match_not_postable",
            details={"invoice_match_id": str(match_id), "status": match.status},
        )


async def post_invoice_match(
    session: AsyncSession, tenant_id: uuid.UUID, match_id: uuid.UUID
) -> InvoiceMatch:
    """Post a MATCHED invoice match (PLAN 6.4, D-042) — the heart. In ONE transaction: raise each PO
    line's billed_quantity, advance the PO toward CLOSED (fully received AND billed), link docflow
    PO→match + GR→match, set the match POSTED, and PUBLISH ``InvoiceMatched`` so finance's handler
    creates + posts the AP vendor bill (Dr GR/IR at PO cost + Dr/Cr PPV / Cr AP at the invoiced
    total), clearing the GR/IR account the goods receipt credited at receipt — the procure-to-pay
    loop closes. A closed invoice period trips the bill's journal trigger and rolls it ALL back.

    Only a MATCHED match can post (an EXCEPTION must be overridden first). A POSTED match is
    idempotent-rejected (terminal). The caller commits via uow; the event drains in the same uow."""
    match = await get_invoice_match(session, tenant_id, match_id)
    _require_postable(match, match_id)

    # Resolve the PPV + AP accounts and the vendor terms up front (downward reads) — raises 422 if a
    # tenant has not mapped them, so the post fails before any state change (D-042).
    ppv_account_id = await finance_queries.purchase_price_variance_account(session, tenant_id)
    ap_account_id = await finance_queries.ap_control_account(session, tenant_id)
    terms_days = (
        await procurement_queries.vendor_payment_terms_days(session, tenant_id, match.vendor_id)
        or 0
    )
    vendor = await procurement_queries.get_vendor(session, tenant_id, match.vendor_id)
    partner_name = vendor.name if vendor is not None else ""

    lines = await get_invoice_match_lines(session, tenant_id, match_id)
    po_lines = {
        line.id: line for line in await po_lines_for(session, tenant_id, match.purchase_order_id)
    }

    bill_lines = _raise_billed_and_build_bill_lines(match, lines, po_lines)
    await _advance_po_status(session, tenant_id, match.purchase_order_id, po_lines.values())

    match.status = MatchStatus.POSTED.value
    match.posted_at = datetime.now()
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, match.document_id, status=MatchStatus.POSTED.value
    )
    await _link_match_predecessors(session, tenant_id, match, lines)

    publish(
        session,
        InvoiceMatched(
            tenant_id=tenant_id,
            match_id=match.id,
            match_number=match.match_number,
            document_id=match.document_id,
            partner_id=match.vendor_id,
            partner_name=partner_name,
            vendor_invoice_ref=match.vendor_invoice_ref,
            invoice_date=match.invoice_date,
            due_date=match.invoice_date + timedelta(days=terms_days),
            currency_code=match.currency_code,
            gr_ir_account_id=match.gr_ir_account_id,
            ppv_account_id=ppv_account_id,
            ap_account_id=ap_account_id,
            tax_code_id=match.tax_code_id,
            lines=tuple(bill_lines),
        ),
    )
    return match


def _raise_billed_and_build_bill_lines(
    match: InvoiceMatch,
    lines: list[InvoiceMatchLine],
    po_lines: dict[uuid.UUID, object],
) -> list[InvoiceMatchBillLine]:
    """Raise each PO line's billed_quantity by its matched quantity and build the per-line bill
    payload finance's handler posts: the GR/IR portion at PO cost + the price variance + the
    invoiced net (PLAN 6.4). The PO lines are mutated in-session."""
    bill_lines: list[InvoiceMatchBillLine] = []
    for line in lines:
        po_line = po_lines[line.purchase_order_line_id]
        po_line.billed_quantity = Decimal(str(po_line.billed_quantity)) + Decimal(  # type: ignore[attr-defined]
            str(line.matched_quantity)
        )
        gr_ir_amount = quantize_for_currency(
            Decimal(str(line.matched_quantity)) * Decimal(str(line.po_unit_cost)),
            match.currency_code,
        )
        bill_lines.append(
            InvoiceMatchBillLine(
                item_id=line.item_id,
                gr_ir_amount=gr_ir_amount,
                price_variance=Decimal(str(line.price_variance)),
                net_amount=Decimal(str(line.line_amount)),
            )
        )
    return bill_lines


async def _link_match_predecessors(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    match: InvoiceMatch,
    lines: list[InvoiceMatchLine],
) -> None:
    """Link the match's predecessor documents (PLAN 6.4): PO → 'matched_by' → match, and each
    distinct goods receipt feeding the match → 'matched_by' → match. The match → bill edge is
    written by finance's handler when it posts the bill (D-042)."""
    po = await session.get(PurchaseOrder, match.purchase_order_id)
    if po is not None:
        await docflow.link_documents(
            session,
            tenant_id,
            predecessor=po.document_id,
            successor=match.document_id,
            link_type=PO_MATCHED_BY_INVOICE_MATCH_LINK,
        )
    linked_grs: set[uuid.UUID] = set()
    for line in lines:
        if line.goods_receipt_line_id is None:
            continue
        gr_line = await session.get(GoodsReceiptLine, line.goods_receipt_line_id)
        if gr_line is None or gr_line.gr_id in linked_grs:
            continue
        gr = await procurement_queries.get_goods_receipt(session, tenant_id, gr_line.gr_id)
        if gr is not None:
            await docflow.link_documents(
                session,
                tenant_id,
                predecessor=gr.document_id,
                successor=match.document_id,
                link_type=GR_MATCHED_BY_INVOICE_MATCH_LINK,
            )
            linked_grs.add(gr_line.gr_id)


async def _advance_po_status(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    po_id: uuid.UUID,
    po_lines,
) -> None:
    """Advance the PO to CLOSED when every line is fully RECEIVED and fully BILLED (PLAN 6.4): the
    procure-to-pay end state. Otherwise the PO stays where the receipt left it (PARTIALLY_RECEIVED /
    RECEIVED) — more goods or invoices are outstanding. The lines are already mutated in-session."""
    fully_billed = all(
        Decimal(str(line.received_quantity)) >= Decimal(str(line.quantity))
        and Decimal(str(line.billed_quantity)) >= Decimal(str(line.quantity))
        for line in po_lines
    )
    if not fully_billed:
        return
    po = await session.get(PurchaseOrder, po_id)
    if po is None or po.tenant_id != tenant_id:
        return
    po.status = PurchaseOrderStatus.CLOSED.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, po.document_id, status=PurchaseOrderStatus.CLOSED.value
    )
