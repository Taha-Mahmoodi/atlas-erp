"""3-way invoice-match create path (PLAN 6.4, D-042): the DRAFT create + its validation/variance/
tolerance helpers + the shared ``po_lines_for`` read. The post / override / cancel actions live in
``invoice_match_post.py`` and the reads + tolerance config in ``invoice_match_reads.py`` (split at
the 400-line cap, the goods_receipts precedent); ``__init__`` re-exports them as one surface.

A 3-way match compares a vendor's invoice against the PO (price) and the goods receipt (quantity).
``create_invoice_match`` writes a DRAFT (validates the PO is at least partially received, each line
belongs to it, the matched quantity is within received − already-billed → the over-billing
constraint, computes the per-line price/quantity variance and evaluates the tolerance band) and
claims the MATCH number at creation (D-040). The status is MATCHED when every line is within
tolerance, EXCEPTION when any line exceeds it (EXCEPTION blocks posting until overridden).

Cross-module rule (STRUCTURE §5 / D-042): procurement NEVER calls finance's service — the bill is
created in FINANCE via the event bus when the match is POSTED. Create only reads the GR/IR account
via finance/queries (downward) to snapshot it; the bill posting lives in the post path.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ValidationFailedError
from app.core.money import quantize_for_currency
from app.modules.finance import queries as finance_queries
from app.modules.procurement.constants import (
    INVOICE_MATCH_DOC_TYPE,
    INVOICE_MATCH_NUMBER_PADDING,
    INVOICE_MATCH_NUMBER_PREFIX,
    INVOICE_MATCH_SEQUENCE_NAME,
    MatchStatus,
    PurchaseOrderStatus,
)
from app.modules.procurement.models import (
    GoodsReceiptLine,
    InvoiceMatch,
    InvoiceMatchLine,
    PurchaseOrder,
    PurchaseOrderLine,
)
from app.modules.procurement.schemas import InvoiceMatchCreate
from app.modules.procurement.service._shared import claim_document_number, validate_quantity
from app.modules.procurement.service.invoice_match_reads import resolve_tolerances

# A PO is matchable once goods have been received against it (PARTIALLY_RECEIVED / RECEIVED): there
# must be received-not-billed quantity to invoice. A DRAFT / SENT / CLOSED / CANCELLED PO cannot
# start a match (nothing received, or already fully closed).
_MATCHABLE_PO_STATUSES = frozenset(
    {PurchaseOrderStatus.PARTIALLY_RECEIVED, PurchaseOrderStatus.RECEIVED}
)

_HUNDRED = Decimal(100)


@dataclass(frozen=True)
class _MatchLineInput:
    """One validated match line: the PO line it bills against, the GR line it draws from (optional),
    the snapshot item + PO cost, the matched quantity, the invoiced unit price, the computed
    variances + line amount and whether it passed the tolerance band."""

    purchase_order_line_id: uuid.UUID
    goods_receipt_line_id: uuid.UUID | None
    item_id: uuid.UUID
    po_unit_cost: Decimal
    matched_quantity: Decimal
    unit_price: Decimal
    price_variance: Decimal
    quantity_variance: Decimal
    line_amount: Decimal
    within_tolerance: bool


async def _require_matchable_po(
    session: AsyncSession, tenant_id: uuid.UUID, po_id: uuid.UUID
) -> PurchaseOrder:
    po = await session.get(PurchaseOrder, po_id)
    if po is None or po.tenant_id != tenant_id:
        raise ValidationFailedError(
            message="Referenced purchase order does not exist",
            code="procurement.purchase_order_not_found",
            details={"purchase_order_id": str(po_id)},
        )
    if PurchaseOrderStatus(po.status) not in _MATCHABLE_PO_STATUSES:
        raise ValidationFailedError(
            message=f"A {po.status} purchase order has no received goods to invoice-match",
            code="procurement.po_not_matchable",
            details={"purchase_order_id": str(po_id), "status": po.status},
        )
    return po


def _within(variance_pct: Decimal, tolerance_pct: Decimal) -> bool:
    """Whether an absolute percentage deviation is within (≤) the tolerance band."""
    return abs(variance_pct) <= tolerance_pct


async def _validate_gr_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    po_line_id: uuid.UUID,
    gr_line_id: uuid.UUID,
) -> None:
    """The referenced GR line must exist and belong to the SAME PO line (the receipt this match
    line draws from). Guards against pointing a match at an unrelated receipt."""
    gr_line = await session.get(GoodsReceiptLine, gr_line_id)
    if (
        gr_line is None
        or gr_line.tenant_id != tenant_id
        or gr_line.purchase_order_line_id != po_line_id
    ):
        raise ValidationFailedError(
            message="The goods-receipt line does not belong to this purchase-order line",
            code="procurement.match_gr_line_mismatch",
            details={"goods_receipt_line_id": str(gr_line_id)},
        )


async def _validate_match_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    po_id: uuid.UUID,
    po_lines: dict[uuid.UUID, PurchaseOrderLine],
    payload_line: object,
    *,
    price_tol: Decimal,
    qty_tol: Decimal,
    currency_code: str,
) -> _MatchLineInput:
    """Validate one match line: the line belongs to the PO, the matched quantity is > 0 and within
    received − already-billed (over-billing REJECTED 422 — no billing beyond goods receipt), compute
    the price/quantity variance against the PO cost and evaluate the tolerance band."""
    po_line_id = payload_line.purchase_order_line_id  # type: ignore[attr-defined]
    po_line = po_lines.get(po_line_id)
    if po_line is None:
        raise ValidationFailedError(
            message="The match line does not belong to this purchase order",
            code="procurement.match_line_not_on_po",
            details={"purchase_order_id": str(po_id), "purchase_order_line_id": str(po_line_id)},
        )
    gr_line_id = payload_line.goods_receipt_line_id  # type: ignore[attr-defined]
    if gr_line_id is not None:
        await _validate_gr_line(session, tenant_id, po_line_id, gr_line_id)

    qty = validate_quantity(payload_line.matched_quantity)  # type: ignore[attr-defined]
    open_to_bill = Decimal(str(po_line.received_quantity)) - Decimal(str(po_line.billed_quantity))
    if qty > open_to_bill:
        raise ValidationFailedError(
            message="The matched quantity exceeds the received-not-yet-billed quantity",
            code="procurement.over_billing",
            details={
                "purchase_order_line_id": str(po_line.id),
                "open_to_bill_quantity": str(open_to_bill),
                "matched_quantity": str(qty),
            },
        )

    po_unit_cost = Decimal(str(po_line.unit_cost))
    unit_price = Decimal(str(payload_line.unit_price))  # type: ignore[attr-defined]
    if unit_price < 0:
        raise ValidationFailedError(
            message="A match line unit price cannot be negative",
            code="procurement.match_unit_price_invalid",
            details={"unit_price": str(unit_price)},
        )
    price_variance = quantize_for_currency((unit_price - po_unit_cost) * qty, currency_code)
    line_amount = quantize_for_currency(unit_price * qty, currency_code)
    # Quantity variance is matched vs the still-open-to-bill quantity (what we expected to invoice).
    quantity_variance = qty - open_to_bill
    price_pct = (
        (abs(unit_price - po_unit_cost) / po_unit_cost) * _HUNDRED
        if po_unit_cost > 0
        else (Decimal(0) if unit_price == 0 else _HUNDRED)
    )
    qty_pct = (
        (abs(quantity_variance) / open_to_bill) * _HUNDRED if open_to_bill > 0 else Decimal(0)
    )
    within_tolerance = _within(price_pct, price_tol) and _within(qty_pct, qty_tol)
    return _MatchLineInput(
        purchase_order_line_id=po_line.id,
        goods_receipt_line_id=gr_line_id,
        item_id=po_line.item_id,
        po_unit_cost=po_unit_cost,
        matched_quantity=qty,
        unit_price=unit_price,
        price_variance=price_variance,
        quantity_variance=quantity_variance,
        line_amount=line_amount,
        within_tolerance=within_tolerance,
    )


async def create_invoice_match(
    session: AsyncSession, tenant_id: uuid.UUID, payload: InvoiceMatchCreate
) -> InvoiceMatch:
    """Create a DRAFT 3-way match against a PO (PLAN 6.4, D-042). Validates the PO is at least
    partially received, each line belongs to it, the matched quantity is within received −
    already-billed (over-billing → 422 procurement.over_billing), computes the per-line price /
    quantity variance and evaluates the tolerance band. The status is MATCHED when EVERY line is
    within tolerance, EXCEPTION when ANY line exceeds it. Snapshots the vendor + GR/IR account and
    claims the MATCH number at creation (D-040). No bill yet — that is POST."""
    if not payload.lines:
        raise ValidationFailedError(
            message="An invoice match needs at least one line",
            code="procurement.match_no_lines",
        )
    po = await _require_matchable_po(session, tenant_id, payload.purchase_order_id)
    po_lines = {line.id: line for line in await po_lines_for(session, tenant_id, po.id)}
    invoice_date = payload.invoice_date or date.today()
    price_tol, qty_tol = await resolve_tolerances(session, tenant_id)
    # The GR/IR account the triggered bill will debit — resolved up front so a tenant that has not
    # mapped it fails at create, not mid-post (finance/queries, downward; raises 422 if unmapped).
    gr_ir_account_id = await finance_queries.gr_ir_clearing_account(session, tenant_id)

    validated = [
        await _validate_match_line(
            session,
            tenant_id,
            po.id,
            po_lines,
            line,
            price_tol=price_tol,
            qty_tol=qty_tol,
            currency_code=po.currency_code,
        )
        for line in payload.lines
    ]
    total_amount = sum((line.line_amount for line in validated), Decimal(0))
    all_within = all(line.within_tolerance for line in validated)
    status = MatchStatus.MATCHED if all_within else MatchStatus.EXCEPTION

    match_id = uuid.uuid4()
    document = await docflow.register_document(
        session, tenant_id, INVOICE_MATCH_DOC_TYPE, match_id, doc_number=None, status=status.value
    )
    number = await claim_document_number(
        session,
        tenant_id,
        sequence_name=INVOICE_MATCH_SEQUENCE_NAME,
        prefix=INVOICE_MATCH_NUMBER_PREFIX,
        padding=INVOICE_MATCH_NUMBER_PADDING,
        on_date=invoice_date,
    )
    match = InvoiceMatch(
        id=match_id,
        tenant_id=tenant_id,
        document_id=document.id,
        match_number=number,
        status=status.value,
        purchase_order_id=po.id,
        vendor_id=po.vendor_id,
        vendor_invoice_ref=payload.vendor_invoice_ref,
        invoice_date=invoice_date,
        currency_code=po.currency_code,
        total_amount=quantize_for_currency(total_amount, po.currency_code),
        tax_code_id=payload.tax_code_id,
        gr_ir_account_id=gr_ir_account_id,
        notes=payload.notes,
    )
    session.add(match)
    for index, line in enumerate(validated, start=1):
        session.add(
            InvoiceMatchLine(
                tenant_id=tenant_id,
                match_id=match_id,
                line_number=index,
                purchase_order_line_id=line.purchase_order_line_id,
                goods_receipt_line_id=line.goods_receipt_line_id,
                item_id=line.item_id,
                matched_quantity=line.matched_quantity,
                unit_price=line.unit_price,
                po_unit_cost=line.po_unit_cost,
                price_variance=line.price_variance,
                quantity_variance=line.quantity_variance,
                line_amount=line.line_amount,
                within_tolerance=line.within_tolerance,
            )
        )
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, document.id, doc_number=number, status=status.value
    )
    return match


async def po_lines_for(
    session: AsyncSession, tenant_id: uuid.UUID, po_id: uuid.UUID
) -> list[PurchaseOrderLine]:
    """The PO's lines (the create + post paths read them to validate / raise billed_quantity). A
    single indexed read on (tenant, po_id); shared with ``invoice_match_post`` (no per-line N+1)."""
    stmt = select(PurchaseOrderLine).where(
        PurchaseOrderLine.tenant_id == tenant_id, PurchaseOrderLine.po_id == po_id
    )
    return list((await session.execute(stmt)).scalars().all())
