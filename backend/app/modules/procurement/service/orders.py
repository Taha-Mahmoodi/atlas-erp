"""Purchase-order business logic (PLAN 6.2): create from scratch, send (approval-gated),
approve/reject, cancel + reads. The convert-from-requisition / convert-from-RFQ paths live in
``conversions.py``; the shared line/total builder + the document writer live here so both the
from-scratch and convert paths produce identical PO rows.

Lifecycle (constants.PurchaseOrderStatus) — states SET in 6.2: DRAFT → (send) PENDING_APPROVAL or
APPROVED → SENT, plus REJECTED / CANCELLED. PARTIALLY_RECEIVED / RECEIVED / CLOSED are driven by 6.3
goods receipts (declared in constants, transitions land later).

Source-control rules enforced at create (D-040): the vendor must be ACTIVE (not BLOCKED/INACTIVE),
and EVERY line item must be in the vendor's approved-items list (else 422
procurement.item_not_approved). ``line_amount`` = qty × unit_cost; ``total_amount`` = Σ line_amount;
``payment_terms_days`` is snapshot from the vendor at create. The PO number is claimed AT CREATION
(D-040). The SEND step evaluates the PURCHASE_ORDER approval threshold on total_amount: ≥ threshold
⇒ PENDING_APPROVAL; below ⇒ auto APPROVED; only an APPROVED PO can be SENT.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.money import quantize_for_currency
from app.core.pagination import (
    DEFAULT_LIMIT,
    OrderKey,
    SortDirection,
    filter_fingerprint,
    paginate,
)
from app.core.schemas import Page
from app.modules.procurement import queries as procurement_queries
from app.modules.procurement.constants import (
    PURCHASE_ORDER_DOC_TYPE,
    PURCHASE_ORDER_NUMBER_PADDING,
    PURCHASE_ORDER_NUMBER_PREFIX,
    PURCHASE_ORDER_SEQUENCE_NAME,
    ApprovalDocumentType,
    PurchaseOrderStatus,
)
from app.modules.procurement.models import PurchaseOrder, PurchaseOrderLine
from app.modules.procurement.schemas import PurchaseOrderCreate
from app.modules.procurement.service import approvals
from app.modules.procurement.service._shared import (
    claim_document_number,
    require_active_vendor,
    require_item_approved_for_vendor,
    validate_item,
    validate_quantity,
)


@dataclass(frozen=True)
class _PoLineInput:
    """The validated, currency-resolved input for one PO line — produced by both the from-scratch
    and convert paths and consumed by ``write_purchase_order``."""

    item_id: uuid.UUID
    description: str | None
    quantity: Decimal
    uom_id: uuid.UUID
    unit_cost: Decimal
    tax_code_id: uuid.UUID | None


async def _resolve_header_defaults(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    vendor_id: uuid.UUID,
    currency_code: str | None,
) -> tuple[str, int]:
    """Resolve the PO's currency + payment-terms snapshot from the vendor when the payload omits
    them. The vendor was already validated ACTIVE by the caller, so its master is present."""
    resolved_currency = currency_code or await procurement_queries.vendor_default_currency(
        session, tenant_id, vendor_id
    )
    if resolved_currency is None:
        raise ValidationFailedError(
            message="The vendor has no default currency and none was supplied",
            code="procurement.po_currency_unresolved",
            details={"vendor_id": str(vendor_id)},
        )
    terms = await procurement_queries.vendor_payment_terms_days(session, tenant_id, vendor_id)
    return resolved_currency, terms or 0


async def write_purchase_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    vendor_id: uuid.UUID,
    currency_code: str,
    payment_terms_days: int,
    order_date: date,
    expected_date: date | None,
    notes: str | None,
    lines: list[_PoLineInput],
    source_requisition_id: uuid.UUID | None = None,
    source_rfq_id: uuid.UUID | None = None,
) -> PurchaseOrder:
    """Write a DRAFT PO header + lines (the shared writer for from-scratch + convert paths). Each
    item is validated approved for the vendor (D-040); ``line_amount`` = qty × unit_cost quantized
    to the currency; ``total_amount`` = Σ line_amount. Claims the PO number + registers the document
    AT CREATION (D-040). The caller has already validated the vendor is ACTIVE."""
    if not lines:
        raise ValidationFailedError(
            message="A purchase order needs at least one line",
            code="procurement.po_no_lines",
        )
    po_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        PURCHASE_ORDER_DOC_TYPE,
        po_id,
        doc_number=None,
        status=PurchaseOrderStatus.DRAFT.value,
    )
    number = await claim_document_number(
        session,
        tenant_id,
        sequence_name=PURCHASE_ORDER_SEQUENCE_NAME,
        prefix=PURCHASE_ORDER_NUMBER_PREFIX,
        padding=PURCHASE_ORDER_NUMBER_PADDING,
        on_date=order_date,
    )

    total = Decimal(0)
    line_rows: list[PurchaseOrderLine] = []
    for index, line in enumerate(lines, start=1):
        await validate_item(session, tenant_id, line.item_id)
        await require_item_approved_for_vendor(session, tenant_id, vendor_id, line.item_id)
        qty = validate_quantity(line.quantity)
        unit_cost = Decimal(str(line.unit_cost))
        if unit_cost < 0:
            raise ValidationFailedError(
                message="A purchase-order unit cost cannot be negative",
                code="procurement.po_unit_cost_invalid",
                details={"item_id": str(line.item_id)},
            )
        line_amount = quantize_for_currency(qty * unit_cost, currency_code)
        total += line_amount
        line_rows.append(
            PurchaseOrderLine(
                tenant_id=tenant_id,
                po_id=po_id,
                line_number=index,
                item_id=line.item_id,
                description=line.description,
                quantity=qty,
                uom_id=line.uom_id,
                unit_cost=unit_cost,
                line_amount=line_amount,
                received_quantity=Decimal(0),
                tax_code_id=line.tax_code_id,
            )
        )

    po = PurchaseOrder(
        id=po_id,
        tenant_id=tenant_id,
        document_id=document.id,
        po_number=number,
        status=PurchaseOrderStatus.DRAFT.value,
        vendor_id=vendor_id,
        currency_code=currency_code,
        order_date=order_date,
        expected_date=expected_date,
        payment_terms_days=payment_terms_days,
        total_amount=total,
        notes=notes,
        source_requisition_id=source_requisition_id,
        source_rfq_id=source_rfq_id,
    )
    session.add(po)
    for row in line_rows:
        session.add(row)
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, document.id, doc_number=number, status=PurchaseOrderStatus.DRAFT.value
    )
    return po


async def get_purchase_order(
    session: AsyncSession, tenant_id: uuid.UUID, po_id: uuid.UUID
) -> PurchaseOrder:
    po = await session.get(PurchaseOrder, po_id)
    if po is None or po.tenant_id != tenant_id:
        raise NotFoundError(
            message="Purchase order not found", code="procurement.purchase_order_not_found"
        )
    return po


async def get_purchase_order_lines(
    session: AsyncSession, tenant_id: uuid.UUID, po_id: uuid.UUID
) -> list[PurchaseOrderLine]:
    stmt = (
        select(PurchaseOrderLine)
        .where(PurchaseOrderLine.tenant_id == tenant_id, PurchaseOrderLine.po_id == po_id)
        .order_by(PurchaseOrderLine.line_number)
    )
    return list((await session.execute(stmt)).scalars().all())


async def create_purchase_order(
    session: AsyncSession, tenant_id: uuid.UUID, payload: PurchaseOrderCreate
) -> PurchaseOrder:
    """Create a DRAFT PO from scratch (PLAN 6.2). Validates the vendor is ACTIVE and resolves the
    currency / payment-terms snapshot from it when omitted, then writes the document via the shared
    writer (which enforces approved-items + computes amounts)."""
    await require_active_vendor(session, tenant_id, payload.vendor_id)
    currency, terms = await _resolve_header_defaults(
        session, tenant_id, payload.vendor_id, payload.currency_code
    )
    lines = [
        _PoLineInput(
            item_id=line.item_id,
            description=line.description,
            quantity=Decimal(str(line.quantity)),
            uom_id=line.uom_id,
            unit_cost=Decimal(str(line.unit_cost)),
            tax_code_id=line.tax_code_id,
        )
        for line in payload.lines
    ]
    return await write_purchase_order(
        session,
        tenant_id,
        vendor_id=payload.vendor_id,
        currency_code=currency,
        payment_terms_days=terms,
        order_date=payload.order_date or date.today(),
        expected_date=payload.expected_date,
        notes=payload.notes,
        lines=lines,
    )


async def send_purchase_order(
    session: AsyncSession, tenant_id: uuid.UUID, po_id: uuid.UUID
) -> PurchaseOrder:
    """Send a PO to its vendor (PLAN 6.2). On a DRAFT PO this evaluates the PURCHASE_ORDER approval
    threshold on total_amount: ≥ threshold ⇒ PENDING_APPROVAL (an approver must clear it before it
    can be sent); below ⇒ auto APPROVED then SENT. An already-APPROVED PO is sent directly. A
    PENDING_APPROVAL / REJECTED / SENT+ PO cannot be (re-)sent here."""
    po = await get_purchase_order(session, tenant_id, po_id)
    status = PurchaseOrderStatus(po.status)

    if status == PurchaseOrderStatus.DRAFT:
        needs_approval = await approvals.requires_approval(
            session,
            tenant_id,
            ApprovalDocumentType.PURCHASE_ORDER,
            Decimal(str(po.total_amount)),
            po.currency_code,
        )
        if needs_approval:
            po.status = PurchaseOrderStatus.PENDING_APPROVAL.value
            await session.flush()
            await docflow.set_document_status(
                session, tenant_id, po.document_id, status=po.status
            )
            return po
        # Below threshold: auto-approve straight through to SENT.
        po.status = PurchaseOrderStatus.SENT.value
        po.approved_at = datetime.now()
        await session.flush()
        await docflow.set_document_status(session, tenant_id, po.document_id, status=po.status)
        return po

    if status == PurchaseOrderStatus.APPROVED:
        po.status = PurchaseOrderStatus.SENT.value
        await session.flush()
        await docflow.set_document_status(session, tenant_id, po.document_id, status=po.status)
        return po

    raise ConflictError(
        message=f"A {po.status} purchase order cannot be sent",
        code="procurement.po_not_sendable",
        details={"status": po.status},
    )


async def decide_purchase_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    po_id: uuid.UUID,
    *,
    approved: bool,
    approver_id: uuid.UUID | None,
) -> PurchaseOrder:
    """Approve or reject a PENDING_APPROVAL PO (PLAN 6.2, the procurement.po.approve action). An
    APPROVED PO records ``approved_by`` / ``approved_at`` and is then sendable; a REJECTED PO is
    terminal."""
    po = await get_purchase_order(session, tenant_id, po_id)
    if PurchaseOrderStatus(po.status) != PurchaseOrderStatus.PENDING_APPROVAL:
        raise ConflictError(
            message="Only a purchase order pending approval can be approved or rejected",
            code="procurement.po_not_pending_approval",
            details={"status": po.status},
        )
    if approved:
        po.status = PurchaseOrderStatus.APPROVED.value
        po.approved_by = approver_id
        po.approved_at = datetime.now()
    else:
        po.status = PurchaseOrderStatus.REJECTED.value
    await session.flush()
    await docflow.set_document_status(session, tenant_id, po.document_id, status=po.status)
    return po


async def cancel_purchase_order(
    session: AsyncSession, tenant_id: uuid.UUID, po_id: uuid.UUID
) -> PurchaseOrder:
    """Cancel a PO (PLAN 6.2). Forbidden once any goods have been received (6.3) or if already
    terminal — a received PO is corrected by a reversing receipt, not a cancel."""
    po = await get_purchase_order(session, tenant_id, po_id)
    status = PurchaseOrderStatus(po.status)
    if status in (
        PurchaseOrderStatus.PARTIALLY_RECEIVED,
        PurchaseOrderStatus.RECEIVED,
        PurchaseOrderStatus.CLOSED,
        PurchaseOrderStatus.REJECTED,
        PurchaseOrderStatus.CANCELLED,
    ):
        raise ConflictError(
            message=f"A {po.status} purchase order cannot be cancelled",
            code="procurement.po_not_cancellable",
            details={"status": po.status},
        )
    po.status = PurchaseOrderStatus.CANCELLED.value
    await session.flush()
    await docflow.set_document_status(session, tenant_id, po.document_id, status=po.status)
    return po


async def list_purchase_orders(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    status: PurchaseOrderStatus | None = None,
    vendor_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[PurchaseOrder]:
    """Keyset-paginated PO list, newest first (D-014). status + vendor filters fold into the cursor
    fingerprint; the (tenant, status) / (tenant, vendor_id, status) indexes serve the filtered page
    (PERFORMANCE §1)."""
    stmt = select(PurchaseOrder).where(PurchaseOrder.tenant_id == tenant_id)
    if status is not None:
        stmt = stmt.where(PurchaseOrder.status == PurchaseOrderStatus(status).value)
    if vendor_id is not None:
        stmt = stmt.where(PurchaseOrder.vendor_id == vendor_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(PurchaseOrder.created_at, SortDirection.DESC)],
        pk=PurchaseOrder.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(status, vendor_id),
    )
