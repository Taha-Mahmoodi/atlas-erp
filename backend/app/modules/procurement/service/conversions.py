"""P2P conversions (PLAN 6.2): requisition → RFQ, requisition → PO, RFQ → PO.

Each conversion copies the predecessor's lines into the successor, links the two registry entries
with a docflow edge (the D-012 chain the DocFlowViewer renders), sets the successor's ``source_*``
id, and advances the predecessor's status (a converted requisition → CONVERTED; a quoted RFQ that
becomes a PO → CLOSED). The successor is created through the from-scratch writers in ``rfqs`` /
``orders`` so it goes through the SAME validation + numbering + document registration (no second
code path). Idempotency (D-013) is owned by the endpoints.

Conversion preconditions:
- requisition → RFQ / requisition → PO: the requisition must be APPROVED (an unapproved request
  cannot be sourced/ordered).
- RFQ → PO: the RFQ must be QUOTED (a PO needs negotiated prices); the PO takes its unit costs from
  the RFQ's ``quoted_unit_cost`` and its vendor from the RFQ. A line without a quote is rejected.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ConflictError, ValidationFailedError
from app.modules.procurement.constants import (
    REQUISITION_ORDERED_BY_PO_LINK,
    REQUISITION_SOURCED_BY_RFQ_LINK,
    RFQ_ORDERED_BY_PO_LINK,
    RequisitionStatus,
    RfqStatus,
)
from app.modules.procurement.models import PurchaseOrder, Rfq
from app.modules.procurement.schemas import (
    PurchaseOrderFromRequisition,
    PurchaseOrderFromRfq,
    RfqCreate,
    RfqFromRequisition,
    RfqLineCreate,
)
from app.modules.procurement.service import orders, requisitions, rfqs
from app.modules.procurement.service._shared import require_active_vendor, validate_currency
from app.modules.procurement.service.orders import _PoLineInput, write_purchase_order


async def _require_approved_requisition(
    session: AsyncSession, tenant_id: uuid.UUID, requisition_id: uuid.UUID
):
    req = await requisitions.get_requisition(session, tenant_id, requisition_id)
    if RequisitionStatus(req.status) != RequisitionStatus.APPROVED:
        raise ConflictError(
            message="Only an approved requisition can be converted",
            code="procurement.requisition_not_approved",
            details={"status": req.status},
        )
    return req


async def convert_requisition_to_rfq(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    requisition_id: uuid.UUID,
    payload: RfqFromRequisition,
) -> Rfq:
    """Source an APPROVED requisition into an RFQ (PLAN 6.2): copy lines, create the RFQ via the
    from-scratch writer, link docflow requisition→rfq ('sourced_by'), set source_requisition_id, and
    mark the requisition CONVERTED."""
    req = await _require_approved_requisition(session, tenant_id, requisition_id)
    req_lines = await requisitions.get_requisition_lines(session, tenant_id, requisition_id)
    currency = payload.currency_code or (req_lines[0].currency_code if req_lines else None)
    if currency is None:
        raise ValidationFailedError(
            message="The requisition has no line currency and none was supplied",
            code="procurement.rfq_currency_unresolved",
        )
    await validate_currency(session, tenant_id, currency)
    await require_active_vendor(session, tenant_id, payload.vendor_id)

    rfq = await rfqs.create_rfq(
        session,
        tenant_id,
        RfqCreate(
            vendor_id=payload.vendor_id,
            currency_code=currency,
            valid_until=payload.valid_until,
            notes=payload.notes,
            lines=[
                RfqLineCreate(
                    item_id=line.item_id,
                    description=line.description,
                    quantity=Decimal(str(line.quantity)),
                    uom_id=line.uom_id,
                )
                for line in req_lines
            ],
        ),
    )
    rfq.source_requisition_id = requisition_id
    await session.flush()
    await docflow.link_documents(
        session,
        tenant_id,
        predecessor=req.document_id,
        successor=rfq.document_id,
        link_type=REQUISITION_SOURCED_BY_RFQ_LINK,
    )
    req.status = RequisitionStatus.CONVERTED.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, req.document_id, status=RequisitionStatus.CONVERTED.value
    )
    return rfq


async def convert_requisition_to_po(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    requisition_id: uuid.UUID,
    payload: PurchaseOrderFromRequisition,
) -> PurchaseOrder:
    """Order an APPROVED requisition straight into a PO (PLAN 6.2): copy lines with unit_cost from
    the requisition estimate, snapshot the vendor's terms/currency, write the PO (which enforces the
    vendor-ACTIVE + approved-items rules), link docflow requisition→po ('ordered_by'), set
    source_requisition_id, and mark the requisition CONVERTED. A line without an estimated cost is
    rejected (a PO line needs a price)."""
    req = await _require_approved_requisition(session, tenant_id, requisition_id)
    req_lines = await requisitions.get_requisition_lines(session, tenant_id, requisition_id)
    await require_active_vendor(session, tenant_id, payload.vendor_id)
    currency, terms = await orders._resolve_header_defaults(
        session, tenant_id, payload.vendor_id, None
    )

    po_lines: list[_PoLineInput] = []
    for line in req_lines:
        if line.estimated_unit_cost is None:
            raise ValidationFailedError(
                message="A requisition line has no estimated cost; a PO line needs a price",
                code="procurement.requisition_line_no_estimate",
                details={"item_id": str(line.item_id)},
            )
        po_lines.append(
            _PoLineInput(
                item_id=line.item_id,
                description=line.description,
                quantity=Decimal(str(line.quantity)),
                uom_id=line.uom_id,
                unit_cost=Decimal(str(line.estimated_unit_cost)),
                tax_code_id=None,
            )
        )
    po = await write_purchase_order(
        session,
        tenant_id,
        vendor_id=payload.vendor_id,
        currency_code=currency,
        payment_terms_days=terms,
        order_date=payload.order_date or date.today(),
        expected_date=payload.expected_date,
        notes=payload.notes,
        lines=po_lines,
        source_requisition_id=requisition_id,
    )
    await docflow.link_documents(
        session,
        tenant_id,
        predecessor=req.document_id,
        successor=po.document_id,
        link_type=REQUISITION_ORDERED_BY_PO_LINK,
    )
    req.status = RequisitionStatus.CONVERTED.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, req.document_id, status=RequisitionStatus.CONVERTED.value
    )
    return po


async def convert_rfq_to_po(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rfq_id: uuid.UUID,
    payload: PurchaseOrderFromRfq,
) -> PurchaseOrder:
    """Order a QUOTED RFQ into a PO (PLAN 6.2): copy lines with unit_cost from the RFQ's quoted
    prices, take the vendor + currency from the RFQ, snapshot the vendor's terms, write the PO, link
    docflow rfq→po ('ordered_by'), set source_rfq_id, and CLOSE the RFQ. A line without a quote is
    rejected."""
    rfq = await rfqs.get_rfq(session, tenant_id, rfq_id)
    if RfqStatus(rfq.status) != RfqStatus.QUOTED:
        raise ConflictError(
            message="Only a quoted RFQ can be converted to a purchase order",
            code="procurement.rfq_not_quoted",
            details={"status": rfq.status},
        )
    await require_active_vendor(session, tenant_id, rfq.vendor_id)
    rfq_lines = await rfqs.get_rfq_lines(session, tenant_id, rfq_id)
    _, terms = await orders._resolve_header_defaults(session, tenant_id, rfq.vendor_id, None)

    po_lines: list[_PoLineInput] = []
    for line in rfq_lines:
        if line.quoted_unit_cost is None:
            raise ValidationFailedError(
                message="An RFQ line has no quoted cost; a PO line needs a price",
                code="procurement.rfq_line_no_quote",
                details={"item_id": str(line.item_id)},
            )
        po_lines.append(
            _PoLineInput(
                item_id=line.item_id,
                description=line.description,
                quantity=Decimal(str(line.quantity)),
                uom_id=line.uom_id,
                unit_cost=Decimal(str(line.quoted_unit_cost)),
                tax_code_id=None,
            )
        )
    po = await write_purchase_order(
        session,
        tenant_id,
        vendor_id=rfq.vendor_id,
        currency_code=rfq.currency_code,
        payment_terms_days=terms,
        order_date=payload.order_date or date.today(),
        expected_date=payload.expected_date,
        notes=payload.notes,
        lines=po_lines,
        source_rfq_id=rfq_id,
    )
    await docflow.link_documents(
        session,
        tenant_id,
        predecessor=rfq.document_id,
        successor=po.document_id,
        link_type=RFQ_ORDERED_BY_PO_LINK,
    )
    rfq.status = RfqStatus.CLOSED.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, rfq.document_id, status=RfqStatus.CLOSED.value
    )
    return po
