"""Purchase-order service tests (PLAN 6.2): create from scratch / requisition / RFQ with docflow +
source ids + computed line/total amounts; vendor-must-be-ACTIVE; item-must-be-approved-for-vendor
(422); approval gating on send (above-threshold → PENDING_APPROVAL, below → auto-approve → SENT);
approve → send. Exercises the real service layer under the tenant context (D-025).
"""

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.procurement import service
from app.modules.procurement.constants import (
    REQUISITION_ORDERED_BY_PO_LINK,
    RFQ_ORDERED_BY_PO_LINK,
    ApprovalDocumentType,
    PurchaseOrderStatus,
    RfqStatus,
    VendorStatus,
)
from app.modules.procurement.schemas import (
    PurchaseOrderCreate,
    PurchaseOrderFromRequisition,
    PurchaseOrderFromRfq,
    PurchaseOrderLineCreate,
    RecordQuotePayload,
    RfqLineQuote,
)
from tests.modules.procurement.conftest import ProcurementSetup
from tests.modules.procurement.factories import (
    build_approval_rule,
    build_approved_item,
    build_po,
    build_requisition,
    build_rfq,
    build_vendor,
)


async def _active_vendor_with_approved_item(
    db_session: AsyncSession, setup: ProcurementSetup
):
    """An ACTIVE vendor whose approved-items list includes the setup item."""
    vendor = await build_vendor(db_session, setup.tenant_id)
    await build_approved_item(db_session, setup.tenant_id, vendor.id, setup.item_id)
    return vendor


async def test_create_po_computes_amounts(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """line_amount = qty × unit_cost; total_amount = Σ line_amount; payment terms snapshot."""
    vendor = await _active_vendor_with_approved_item(db_session, procurement_setup)
    po = await build_po(
        db_session,
        procurement_setup.tenant_id,
        vendor_id=vendor.id,
        item_id=procurement_setup.item_id,
        uom_id=procurement_setup.uom_id,
        quantity="10",
        unit_cost="5",
    )
    assert po.status == PurchaseOrderStatus.DRAFT.value
    assert po.po_number.startswith("PO-")
    assert Decimal(str(po.total_amount)) == Decimal("50")
    assert po.payment_terms_days == vendor.payment_terms_days
    assert po.currency_code == "USD"
    with tenant_context(procurement_setup.tenant_id):
        lines = await service.get_purchase_order_lines(
            db_session, procurement_setup.tenant_id, po.id
        )
    assert Decimal(str(lines[0].line_amount)) == Decimal("50")
    assert Decimal(str(lines[0].received_quantity)) == Decimal("0")


async def test_create_po_item_not_approved_422(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """A PO line item that is NOT in the vendor's approved list is rejected (the v1 source-control
    rule, code procurement.item_not_approved)."""
    vendor = await build_vendor(db_session, procurement_setup.tenant_id)  # no approved item
    with pytest.raises(ValidationFailedError) as err, tenant_context(procurement_setup.tenant_id):
        await service.create_purchase_order(
            db_session,
            procurement_setup.tenant_id,
            PurchaseOrderCreate(
                vendor_id=vendor.id,
                lines=[
                    PurchaseOrderLineCreate(
                        item_id=procurement_setup.item_id,
                        quantity=Decimal("1"),
                        uom_id=procurement_setup.uom_id,
                        unit_cost=Decimal("5"),
                    )
                ],
            ),
        )
    assert err.value.code == "procurement.item_not_approved"


async def test_create_po_blocked_vendor_422(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """A BLOCKED vendor cannot receive a new PO (code procurement.vendor_not_active)."""
    vendor = await build_vendor(
        db_session, procurement_setup.tenant_id, status=VendorStatus.BLOCKED
    )
    await build_approved_item(
        db_session, procurement_setup.tenant_id, vendor.id, procurement_setup.item_id
    )
    with pytest.raises(ValidationFailedError) as err, tenant_context(procurement_setup.tenant_id):
        await service.create_purchase_order(
            db_session,
            procurement_setup.tenant_id,
            PurchaseOrderCreate(
                vendor_id=vendor.id,
                lines=[
                    PurchaseOrderLineCreate(
                        item_id=procurement_setup.item_id,
                        quantity=Decimal("1"),
                        uom_id=procurement_setup.uom_id,
                        unit_cost=Decimal("5"),
                    )
                ],
            ),
        )
    assert err.value.code == "procurement.vendor_not_active"


async def test_send_below_threshold_auto_approves(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """A PO total below the PURCHASE_ORDER threshold auto-approves on send → SENT."""
    await build_approval_rule(
        db_session,
        procurement_setup.tenant_id,
        document_type=ApprovalDocumentType.PURCHASE_ORDER,
        threshold_amount="1000",
    )
    vendor = await _active_vendor_with_approved_item(db_session, procurement_setup)
    po = await build_po(
        db_session,
        procurement_setup.tenant_id,
        vendor_id=vendor.id,
        item_id=procurement_setup.item_id,
        uom_id=procurement_setup.uom_id,
        quantity="10",
        unit_cost="5",
    )
    with tenant_context(procurement_setup.tenant_id):
        sent = await service.send_purchase_order(db_session, procurement_setup.tenant_id, po.id)
    assert sent.status == PurchaseOrderStatus.SENT.value


async def test_send_above_threshold_then_approve_then_send(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """A PO total at/above the threshold goes PENDING_APPROVAL on send; an approver clears it to
    APPROVED; then it can be SENT."""
    await build_approval_rule(
        db_session,
        procurement_setup.tenant_id,
        document_type=ApprovalDocumentType.PURCHASE_ORDER,
        threshold_amount="100",
    )
    vendor = await _active_vendor_with_approved_item(db_session, procurement_setup)
    po = await build_po(
        db_session,
        procurement_setup.tenant_id,
        vendor_id=vendor.id,
        item_id=procurement_setup.item_id,
        uom_id=procurement_setup.uom_id,
        quantity="100",
        unit_cost="5",
    )
    with tenant_context(procurement_setup.tenant_id):
        pending = await service.send_purchase_order(
            db_session, procurement_setup.tenant_id, po.id
        )
        assert pending.status == PurchaseOrderStatus.PENDING_APPROVAL.value
        approved = await service.decide_purchase_order(
            db_session, procurement_setup.tenant_id, po.id, approved=True, approver_id=None
        )
        assert approved.status == PurchaseOrderStatus.APPROVED.value
        assert approved.approved_at is not None
        sent = await service.send_purchase_order(db_session, procurement_setup.tenant_id, po.id)
    assert sent.status == PurchaseOrderStatus.SENT.value


async def test_reject_pending_po(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    await build_approval_rule(
        db_session,
        procurement_setup.tenant_id,
        document_type=ApprovalDocumentType.PURCHASE_ORDER,
        threshold_amount="0",
    )
    vendor = await _active_vendor_with_approved_item(db_session, procurement_setup)
    po = await build_po(
        db_session,
        procurement_setup.tenant_id,
        vendor_id=vendor.id,
        item_id=procurement_setup.item_id,
        uom_id=procurement_setup.uom_id,
    )
    with tenant_context(procurement_setup.tenant_id):
        await service.send_purchase_order(db_session, procurement_setup.tenant_id, po.id)
        rejected = await service.decide_purchase_order(
            db_session, procurement_setup.tenant_id, po.id, approved=False, approver_id=None
        )
    assert rejected.status == PurchaseOrderStatus.REJECTED.value


async def test_convert_requisition_to_po_links_docflow(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """Converting an APPROVED requisition to a PO copies lines (unit_cost from the estimate), sets
    source_requisition_id, and links docflow requisition→po ('ordered_by')."""
    vendor = await _active_vendor_with_approved_item(db_session, procurement_setup)
    req = await build_requisition(
        db_session,
        procurement_setup.tenant_id,
        item_id=procurement_setup.item_id,
        uom_id=procurement_setup.uom_id,
        quantity="4",
        estimated_unit_cost="9",
    )
    with tenant_context(procurement_setup.tenant_id):
        await service.submit_requisition(db_session, procurement_setup.tenant_id, req.id)
        po = await service.convert_requisition_to_po(
            db_session,
            procurement_setup.tenant_id,
            req.id,
            PurchaseOrderFromRequisition(vendor_id=vendor.id),
        )
        await db_session.commit()
        chain = await docflow.get_document_chain(
            db_session, procurement_setup.tenant_id, req.document_id
        )
    assert po.source_requisition_id == req.id
    assert Decimal(str(po.total_amount)) == Decimal("36")  # 4 × 9
    assert REQUISITION_ORDERED_BY_PO_LINK in {edge.link_type for edge in chain.edges}


async def test_convert_rfq_to_po_uses_quote(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """Converting a QUOTED RFQ to a PO takes unit_cost from the quote, sets source_rfq_id, links
    docflow rfq→po, and CLOSES the RFQ."""
    vendor = await _active_vendor_with_approved_item(db_session, procurement_setup)
    rfq = await build_rfq(
        db_session,
        procurement_setup.tenant_id,
        vendor_id=vendor.id,
        item_id=procurement_setup.item_id,
        uom_id=procurement_setup.uom_id,
        quantity="2",
    )
    with tenant_context(procurement_setup.tenant_id):
        await service.send_rfq(db_session, procurement_setup.tenant_id, rfq.id)
        lines = await service.get_rfq_lines(db_session, procurement_setup.tenant_id, rfq.id)
        await service.record_quote(
            db_session,
            procurement_setup.tenant_id,
            rfq.id,
            RecordQuotePayload(
                quotes=[RfqLineQuote(line_id=lines[0].id, quoted_unit_cost=Decimal("11"))]
            ),
        )
        po = await service.convert_rfq_to_po(
            db_session,
            procurement_setup.tenant_id,
            rfq.id,
            PurchaseOrderFromRfq(),
        )
        await db_session.commit()
        rfq_after = await service.get_rfq(db_session, procurement_setup.tenant_id, rfq.id)
        chain = await docflow.get_document_chain(
            db_session, procurement_setup.tenant_id, rfq.document_id
        )
    assert po.source_rfq_id == rfq.id
    assert Decimal(str(po.total_amount)) == Decimal("22")  # 2 × 11
    assert rfq_after.status == RfqStatus.CLOSED.value
    assert RFQ_ORDERED_BY_PO_LINK in {edge.link_type for edge in chain.edges}


async def test_cancel_draft_po(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    vendor = await _active_vendor_with_approved_item(db_session, procurement_setup)
    po = await build_po(
        db_session,
        procurement_setup.tenant_id,
        vendor_id=vendor.id,
        item_id=procurement_setup.item_id,
        uom_id=procurement_setup.uom_id,
    )
    with tenant_context(procurement_setup.tenant_id):
        cancelled = await service.cancel_purchase_order(
            db_session, procurement_setup.tenant_id, po.id
        )
    assert cancelled.status == PurchaseOrderStatus.CANCELLED.value


async def test_only_approved_po_can_be_sent(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """A PENDING_APPROVAL PO cannot be sent directly (must be approved first)."""
    await build_approval_rule(
        db_session,
        procurement_setup.tenant_id,
        document_type=ApprovalDocumentType.PURCHASE_ORDER,
        threshold_amount="0",
    )
    vendor = await _active_vendor_with_approved_item(db_session, procurement_setup)
    po = await build_po(
        db_session,
        procurement_setup.tenant_id,
        vendor_id=vendor.id,
        item_id=procurement_setup.item_id,
        uom_id=procurement_setup.uom_id,
    )
    with tenant_context(procurement_setup.tenant_id):
        await service.send_purchase_order(db_session, procurement_setup.tenant_id, po.id)
        with pytest.raises(ConflictError):
            await service.send_purchase_order(db_session, procurement_setup.tenant_id, po.id)
