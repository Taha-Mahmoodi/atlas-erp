"""RFQ service tests (PLAN 6.2): create, send, record-quote, close, and the convert-from-requisition
path (docflow link requisition→rfq + source_requisition_id). Exercises the real service layer under
the tenant context (D-025).
"""

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ConflictError
from app.core.tenancy import tenant_context
from app.modules.procurement import service
from app.modules.procurement.constants import (
    REQUISITION_SOURCED_BY_RFQ_LINK,
    RequisitionStatus,
    RfqStatus,
)
from app.modules.procurement.schemas import (
    RecordQuotePayload,
    RfqFromRequisition,
    RfqLineQuote,
)
from tests.modules.procurement.conftest import ProcurementSetup
from tests.modules.procurement.factories import build_requisition, build_rfq, build_vendor


async def test_create_and_send_rfq(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    vendor = await build_vendor(db_session, procurement_setup.tenant_id)
    rfq = await build_rfq(
        db_session,
        procurement_setup.tenant_id,
        vendor_id=vendor.id,
        item_id=procurement_setup.item_id,
        uom_id=procurement_setup.uom_id,
    )
    assert rfq.status == RfqStatus.DRAFT.value
    assert rfq.rfq_number.startswith("RFQ-")
    with tenant_context(procurement_setup.tenant_id):
        sent = await service.send_rfq(db_session, procurement_setup.tenant_id, rfq.id)
    assert sent.status == RfqStatus.SENT.value


async def test_record_quote_advances_to_quoted(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    vendor = await build_vendor(db_session, procurement_setup.tenant_id)
    rfq = await build_rfq(
        db_session,
        procurement_setup.tenant_id,
        vendor_id=vendor.id,
        item_id=procurement_setup.item_id,
        uom_id=procurement_setup.uom_id,
    )
    with tenant_context(procurement_setup.tenant_id):
        await service.send_rfq(db_session, procurement_setup.tenant_id, rfq.id)
        lines = await service.get_rfq_lines(db_session, procurement_setup.tenant_id, rfq.id)
        quoted = await service.record_quote(
            db_session,
            procurement_setup.tenant_id,
            rfq.id,
            RecordQuotePayload(
                quotes=[RfqLineQuote(line_id=lines[0].id, quoted_unit_cost=Decimal("7.50"))]
            ),
        )
        lines = await service.get_rfq_lines(db_session, procurement_setup.tenant_id, rfq.id)
    assert quoted.status == RfqStatus.QUOTED.value
    assert Decimal(str(lines[0].quoted_unit_cost)) == Decimal("7.50")


async def test_record_quote_requires_sent(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """A DRAFT RFQ cannot be quoted (must be SENT first)."""
    vendor = await build_vendor(db_session, procurement_setup.tenant_id)
    rfq = await build_rfq(
        db_session,
        procurement_setup.tenant_id,
        vendor_id=vendor.id,
        item_id=procurement_setup.item_id,
        uom_id=procurement_setup.uom_id,
    )
    with pytest.raises(ConflictError), tenant_context(procurement_setup.tenant_id):
        await service.record_quote(
            db_session, procurement_setup.tenant_id, rfq.id, RecordQuotePayload(quotes=[])
        )


async def test_convert_requisition_to_rfq_links_docflow(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """Converting an APPROVED requisition creates an RFQ that copies the lines, sets
    source_requisition_id, links docflow requisition→rfq ('sourced_by'), and marks the requisition
    CONVERTED."""
    vendor = await build_vendor(db_session, procurement_setup.tenant_id)
    req = await build_requisition(
        db_session,
        procurement_setup.tenant_id,
        item_id=procurement_setup.item_id,
        uom_id=procurement_setup.uom_id,
    )
    with tenant_context(procurement_setup.tenant_id):
        await service.submit_requisition(db_session, procurement_setup.tenant_id, req.id)
        rfq = await service.convert_requisition_to_rfq(
            db_session,
            procurement_setup.tenant_id,
            req.id,
            RfqFromRequisition(vendor_id=vendor.id),
        )
        await db_session.commit()
        req_after = await service.get_requisition(
            db_session, procurement_setup.tenant_id, req.id
        )
        rfq_lines = await service.get_rfq_lines(db_session, procurement_setup.tenant_id, rfq.id)
        chain = await docflow.get_document_chain(
            db_session, procurement_setup.tenant_id, req.document_id
        )
    assert rfq.source_requisition_id == req.id
    assert req_after.status == RequisitionStatus.CONVERTED.value
    assert len(rfq_lines) == 1
    link_types = {edge.link_type for edge in chain.edges}
    assert REQUISITION_SOURCED_BY_RFQ_LINK in link_types


async def test_convert_requires_approved_requisition(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """A DRAFT (unapproved) requisition cannot be converted."""
    vendor = await build_vendor(db_session, procurement_setup.tenant_id)
    req = await build_requisition(
        db_session,
        procurement_setup.tenant_id,
        item_id=procurement_setup.item_id,
        uom_id=procurement_setup.uom_id,
    )
    with pytest.raises(ConflictError), tenant_context(procurement_setup.tenant_id):
        await service.convert_requisition_to_rfq(
            db_session,
            procurement_setup.tenant_id,
            req.id,
            RfqFromRequisition(vendor_id=vendor.id),
        )
