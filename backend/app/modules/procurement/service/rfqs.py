"""RFQ business logic (PLAN 6.2): create from scratch, send, record-quote, close + reads.

Lifecycle (constants.RfqStatus): DRAFT → SENT → QUOTED → CLOSED, or any non-terminal → CANCELLED. An
RFQ targets ONE vendor in v1. The RFQ number is claimed AT CREATION (D-040). RECORD-QUOTE fills the
per-line ``quoted_unit_cost`` and advances SENT→QUOTED. The convert-from-requisition path lives in
``conversions.py`` (it links docflow + copies lines); this module owns the from-scratch + lifecycle
actions. Idempotency (D-013) is owned by the endpoints.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import (
    DEFAULT_LIMIT,
    OrderKey,
    SortDirection,
    filter_fingerprint,
    paginate,
)
from app.core.schemas import Page
from app.modules.procurement.constants import (
    RFQ_DOC_TYPE,
    RFQ_NUMBER_PADDING,
    RFQ_NUMBER_PREFIX,
    RFQ_SEQUENCE_NAME,
    RfqStatus,
)
from app.modules.procurement.models import Rfq, RfqLine
from app.modules.procurement.schemas import RecordQuotePayload, RfqCreate
from app.modules.procurement.service._shared import (
    claim_document_number,
    require_active_vendor,
    validate_currency,
    validate_item,
    validate_quantity,
)


async def get_rfq(session: AsyncSession, tenant_id: uuid.UUID, rfq_id: uuid.UUID) -> Rfq:
    rfq = await session.get(Rfq, rfq_id)
    if rfq is None or rfq.tenant_id != tenant_id:
        raise NotFoundError(message="RFQ not found", code="procurement.rfq_not_found")
    return rfq


async def get_rfq_lines(
    session: AsyncSession, tenant_id: uuid.UUID, rfq_id: uuid.UUID
) -> list[RfqLine]:
    stmt = (
        select(RfqLine)
        .where(RfqLine.tenant_id == tenant_id, RfqLine.rfq_id == rfq_id)
        .order_by(RfqLine.line_number)
    )
    return list((await session.execute(stmt)).scalars().all())


async def create_rfq(
    session: AsyncSession, tenant_id: uuid.UUID, payload: RfqCreate
) -> Rfq:
    """Create a DRAFT RFQ from scratch (PLAN 6.2). Validates the vendor is ACTIVE, every item
    exists, qty > 0 and the currency exists; claims the RFQ number and registers the document."""
    if not payload.lines:
        raise ValidationFailedError(
            message="An RFQ needs at least one line", code="procurement.rfq_no_lines"
        )
    await require_active_vendor(session, tenant_id, payload.vendor_id)
    await validate_currency(session, tenant_id, payload.currency_code)
    for line in payload.lines:
        await validate_item(session, tenant_id, line.item_id)
        validate_quantity(line.quantity)

    rfq_id = uuid.uuid4()
    document = await docflow.register_document(
        session, tenant_id, RFQ_DOC_TYPE, rfq_id, doc_number=None, status=RfqStatus.DRAFT.value
    )
    number = await claim_document_number(
        session,
        tenant_id,
        sequence_name=RFQ_SEQUENCE_NAME,
        prefix=RFQ_NUMBER_PREFIX,
        padding=RFQ_NUMBER_PADDING,
        on_date=datetime.now().date(),
    )
    rfq = Rfq(
        id=rfq_id,
        tenant_id=tenant_id,
        document_id=document.id,
        rfq_number=number,
        status=RfqStatus.DRAFT.value,
        vendor_id=payload.vendor_id,
        currency_code=payload.currency_code,
        valid_until=payload.valid_until,
        notes=payload.notes,
    )
    session.add(rfq)
    for index, line in enumerate(payload.lines, start=1):
        session.add(
            RfqLine(
                tenant_id=tenant_id,
                rfq_id=rfq_id,
                line_number=index,
                item_id=line.item_id,
                description=line.description,
                quantity=validate_quantity(line.quantity),
                uom_id=line.uom_id,
            )
        )
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, document.id, doc_number=number, status=RfqStatus.DRAFT.value
    )
    return rfq


async def send_rfq(session: AsyncSession, tenant_id: uuid.UUID, rfq_id: uuid.UUID) -> Rfq:
    """Issue a DRAFT RFQ to its vendor (PLAN 6.2): DRAFT→SENT."""
    rfq = await get_rfq(session, tenant_id, rfq_id)
    if RfqStatus(rfq.status) != RfqStatus.DRAFT:
        raise ConflictError(
            message="Only a draft RFQ can be sent",
            code="procurement.rfq_not_draft",
            details={"status": rfq.status},
        )
    rfq.status = RfqStatus.SENT.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, rfq.document_id, status=RfqStatus.SENT.value
    )
    return rfq


async def record_quote(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rfq_id: uuid.UUID,
    payload: RecordQuotePayload,
) -> Rfq:
    """Record the vendor's quoted prices on a SENT RFQ (PLAN 6.2): fill ``quoted_unit_cost`` per
    named line, advance SENT→QUOTED. Each quote line must belong to this RFQ and be >= 0."""
    rfq = await get_rfq(session, tenant_id, rfq_id)
    if RfqStatus(rfq.status) != RfqStatus.SENT:
        raise ConflictError(
            message="Only a sent RFQ can be quoted",
            code="procurement.rfq_not_sent",
            details={"status": rfq.status},
        )
    lines = {line.id: line for line in await get_rfq_lines(session, tenant_id, rfq_id)}
    for quote in payload.quotes:
        line = lines.get(quote.line_id)
        if line is None:
            raise ValidationFailedError(
                message="A quote references a line that is not on this RFQ",
                code="procurement.rfq_line_not_found",
                details={"line_id": str(quote.line_id)},
            )
        price = Decimal(str(quote.quoted_unit_cost))
        if price < 0:
            raise ValidationFailedError(
                message="A quoted unit cost cannot be negative",
                code="procurement.rfq_quote_invalid",
                details={"line_id": str(quote.line_id)},
            )
        line.quoted_unit_cost = price
    rfq.status = RfqStatus.QUOTED.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, rfq.document_id, status=RfqStatus.QUOTED.value
    )
    return rfq


async def close_rfq(session: AsyncSession, tenant_id: uuid.UUID, rfq_id: uuid.UUID) -> Rfq:
    """Close an RFQ (PLAN 6.2): sourcing finished. Allowed from SENT/QUOTED; a DRAFT/terminal RFQ
    cannot be closed (cancel a draft instead)."""
    rfq = await get_rfq(session, tenant_id, rfq_id)
    if RfqStatus(rfq.status) not in (RfqStatus.SENT, RfqStatus.QUOTED):
        raise ConflictError(
            message="Only a sent or quoted RFQ can be closed",
            code="procurement.rfq_not_closable",
            details={"status": rfq.status},
        )
    rfq.status = RfqStatus.CLOSED.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, rfq.document_id, status=RfqStatus.CLOSED.value
    )
    return rfq


async def list_rfqs(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    status: RfqStatus | None = None,
    vendor_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[Rfq]:
    """Keyset-paginated RFQ list, newest first (D-014). status + vendor filters fold into the cursor
    fingerprint; the (tenant, status) / (tenant, vendor_id) indexes serve the filtered page."""
    stmt = select(Rfq).where(Rfq.tenant_id == tenant_id)
    if status is not None:
        stmt = stmt.where(Rfq.status == RfqStatus(status).value)
    if vendor_id is not None:
        stmt = stmt.where(Rfq.vendor_id == vendor_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(Rfq.created_at, SortDirection.DESC)],
        pk=Rfq.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(status, vendor_id),
    )
