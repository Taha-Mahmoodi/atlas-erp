"""Purchase-requisition business logic (PLAN 6.2): create, submit (approval-gated), approve/reject,
update, cancel + reads.

Lifecycle (constants.RequisitionStatus): DRAFT → SUBMITTED → APPROVED/REJECTED, or
DRAFT/SUBMITTED/APPROVED → CANCELLED, or APPROVED → CONVERTED (the convert services flip this). The
SUBMIT step evaluates the REQUISITION value-threshold rule on the estimated total
(Σ qty × estimated_unit_cost over the lines): at-or-above the active threshold the requisition STAYS
SUBMITTED awaiting an approver; below it the submit auto-advances to APPROVED (the data-driven rule,
D-040). A line without an estimate contributes 0 to the total — an all-estimate-less requisition has
total 0, which is below any positive threshold, so it auto-approves.

The PR number is claimed AT CREATION (D-040) and the document is registered in core_documents then.
Idempotency (D-013) is owned by the endpoints.
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
    REQUISITION_DOC_TYPE,
    REQUISITION_NUMBER_PADDING,
    REQUISITION_NUMBER_PREFIX,
    REQUISITION_SEQUENCE_NAME,
    ApprovalDocumentType,
    RequisitionStatus,
)
from app.modules.procurement.models import PurchaseRequisition, PurchaseRequisitionLine
from app.modules.procurement.schemas import RequisitionCreate, RequisitionUpdate
from app.modules.procurement.service import approvals
from app.modules.procurement.service._shared import (
    claim_document_number,
    validate_currency,
    validate_item,
    validate_quantity,
)


async def get_requisition(
    session: AsyncSession, tenant_id: uuid.UUID, requisition_id: uuid.UUID
) -> PurchaseRequisition:
    req = await session.get(PurchaseRequisition, requisition_id)
    if req is None or req.tenant_id != tenant_id:
        raise NotFoundError(
            message="Requisition not found", code="procurement.requisition_not_found"
        )
    return req


async def get_requisition_lines(
    session: AsyncSession, tenant_id: uuid.UUID, requisition_id: uuid.UUID
) -> list[PurchaseRequisitionLine]:
    stmt = (
        select(PurchaseRequisitionLine)
        .where(
            PurchaseRequisitionLine.tenant_id == tenant_id,
            PurchaseRequisitionLine.requisition_id == requisition_id,
        )
        .order_by(PurchaseRequisitionLine.line_number)
    )
    return list((await session.execute(stmt)).scalars().all())


async def _validate_lines(
    session: AsyncSession, tenant_id: uuid.UUID, payload_lines: list
) -> None:
    if not payload_lines:
        raise ValidationFailedError(
            message="A requisition needs at least one line",
            code="procurement.requisition_no_lines",
        )
    for line in payload_lines:
        await validate_item(session, tenant_id, line.item_id)
        validate_quantity(line.quantity)
        await validate_currency(session, tenant_id, line.currency_code)


async def create_requisition(
    session: AsyncSession, tenant_id: uuid.UUID, payload: RequisitionCreate
) -> PurchaseRequisition:
    """Create a DRAFT requisition + lines (PLAN 6.2). Validates every item exists, qty > 0 and the
    line currency exists in finance; claims the PR number and registers the document AT CREATION
    (D-040)."""
    await _validate_lines(session, tenant_id, payload.lines)

    requisition_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        REQUISITION_DOC_TYPE,
        requisition_id,
        doc_number=None,
        status=RequisitionStatus.DRAFT.value,
    )
    number = await claim_document_number(
        session,
        tenant_id,
        sequence_name=REQUISITION_SEQUENCE_NAME,
        prefix=REQUISITION_NUMBER_PREFIX,
        padding=REQUISITION_NUMBER_PADDING,
        on_date=datetime.now().date(),
    )
    req = PurchaseRequisition(
        id=requisition_id,
        tenant_id=tenant_id,
        document_id=document.id,
        requisition_number=number,
        status=RequisitionStatus.DRAFT.value,
        requested_by=payload.requested_by,
        needed_by_date=payload.needed_by_date,
        notes=payload.notes,
    )
    session.add(req)
    for index, line in enumerate(payload.lines, start=1):
        session.add(
            PurchaseRequisitionLine(
                tenant_id=tenant_id,
                requisition_id=requisition_id,
                line_number=index,
                item_id=line.item_id,
                description=line.description,
                quantity=validate_quantity(line.quantity),
                uom_id=line.uom_id,
                estimated_unit_cost=(
                    None
                    if line.estimated_unit_cost is None
                    else Decimal(str(line.estimated_unit_cost))
                ),
                currency_code=line.currency_code,
            )
        )
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, document.id, doc_number=number, status=RequisitionStatus.DRAFT.value
    )
    return req


async def update_requisition(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    requisition_id: uuid.UUID,
    payload: RequisitionUpdate,
) -> PurchaseRequisition:
    """Partial header update of a DRAFT requisition (PLAN 6.2). When ``lines`` is supplied they are
    replaced wholesale (revalidated + renumbered). Only a DRAFT requisition is editable."""
    req = await get_requisition(session, tenant_id, requisition_id)
    if RequisitionStatus(req.status) != RequisitionStatus.DRAFT:
        raise ConflictError(
            message="Only a draft requisition can be edited",
            code="procurement.requisition_not_draft",
            details={"status": req.status},
        )
    data = payload.model_dump(exclude_unset=True)
    new_lines = data.pop("lines", None)
    for field, value in data.items():
        setattr(req, field, value)
    if new_lines is not None:
        await _validate_lines(session, tenant_id, payload.lines)
        for existing in await get_requisition_lines(session, tenant_id, requisition_id):
            await session.delete(existing)
        await session.flush()
        for index, line in enumerate(payload.lines, start=1):
            session.add(
                PurchaseRequisitionLine(
                    tenant_id=tenant_id,
                    requisition_id=requisition_id,
                    line_number=index,
                    item_id=line.item_id,
                    description=line.description,
                    quantity=validate_quantity(line.quantity),
                    uom_id=line.uom_id,
                    estimated_unit_cost=(
                        None
                        if line.estimated_unit_cost is None
                        else Decimal(str(line.estimated_unit_cost))
                    ),
                    currency_code=line.currency_code,
                )
            )
    await session.flush()
    return req


async def _estimated_total(
    session: AsyncSession, tenant_id: uuid.UUID, requisition_id: uuid.UUID
) -> tuple[Decimal, str | None]:
    """The requisition's estimated total (Σ qty × estimated_unit_cost) and the currency of its
    lines (the first line's — v1 requisitions are single-currency in practice). A line with no
    estimate contributes 0."""
    lines = await get_requisition_lines(session, tenant_id, requisition_id)
    total = Decimal(0)
    currency: str | None = None
    for line in lines:
        if currency is None:
            currency = line.currency_code
        if line.estimated_unit_cost is not None:
            total += Decimal(str(line.quantity)) * Decimal(str(line.estimated_unit_cost))
    return total, currency


async def submit_requisition(
    session: AsyncSession, tenant_id: uuid.UUID, requisition_id: uuid.UUID
) -> PurchaseRequisition:
    """Submit a DRAFT requisition (PLAN 6.2). Evaluates the REQUISITION approval threshold on the
    estimated total: at-or-above ⇒ status SUBMITTED (awaits an approver); below ⇒ auto APPROVED.
    Idempotent-ish only in that re-submitting a non-draft is a conflict."""
    req = await get_requisition(session, tenant_id, requisition_id)
    if RequisitionStatus(req.status) != RequisitionStatus.DRAFT:
        raise ConflictError(
            message="Only a draft requisition can be submitted",
            code="procurement.requisition_not_draft",
            details={"status": req.status},
        )
    total, currency = await _estimated_total(session, tenant_id, requisition_id)
    needs_approval = currency is not None and await approvals.requires_approval(
        session, tenant_id, ApprovalDocumentType.REQUISITION, total, currency
    )
    new_status = RequisitionStatus.SUBMITTED if needs_approval else RequisitionStatus.APPROVED
    req.status = new_status.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, req.document_id, status=new_status.value
    )
    return req


async def decide_requisition(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    requisition_id: uuid.UUID,
    *,
    approved: bool,
) -> PurchaseRequisition:
    """Approve or reject a SUBMITTED requisition (PLAN 6.2, the procurement.requisition.approve
    action). Only a SUBMITTED requisition awaiting approval can be decided."""
    req = await get_requisition(session, tenant_id, requisition_id)
    if RequisitionStatus(req.status) != RequisitionStatus.SUBMITTED:
        raise ConflictError(
            message="Only a submitted requisition can be approved or rejected",
            code="procurement.requisition_not_submitted",
            details={"status": req.status},
        )
    new_status = RequisitionStatus.APPROVED if approved else RequisitionStatus.REJECTED
    req.status = new_status.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, req.document_id, status=new_status.value
    )
    return req


async def cancel_requisition(
    session: AsyncSession, tenant_id: uuid.UUID, requisition_id: uuid.UUID
) -> PurchaseRequisition:
    """Cancel a requisition (PLAN 6.2). Allowed from DRAFT/SUBMITTED/APPROVED; a CONVERTED one
    cannot be cancelled (it has a successor) and a terminal one cannot be re-cancelled."""
    req = await get_requisition(session, tenant_id, requisition_id)
    status = RequisitionStatus(req.status)
    if status in (
        RequisitionStatus.CONVERTED,
        RequisitionStatus.REJECTED,
        RequisitionStatus.CANCELLED,
    ):
        raise ConflictError(
            message=f"A {req.status} requisition cannot be cancelled",
            code="procurement.requisition_not_cancellable",
            details={"status": req.status},
        )
    req.status = RequisitionStatus.CANCELLED.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, req.document_id, status=RequisitionStatus.CANCELLED.value
    )
    return req


async def list_requisitions(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    status: RequisitionStatus | None = None,
    requested_by: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[PurchaseRequisition]:
    """Keyset-paginated requisition list, newest first (D-014). status + requested_by filters fold
    into the cursor fingerprint; the (tenant, status) index serves the filtered page."""
    stmt = select(PurchaseRequisition).where(PurchaseRequisition.tenant_id == tenant_id)
    if status is not None:
        stmt = stmt.where(PurchaseRequisition.status == RequisitionStatus(status).value)
    if requested_by is not None:
        stmt = stmt.where(PurchaseRequisition.requested_by == requested_by)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(PurchaseRequisition.created_at, SortDirection.DESC)],
        pk=PurchaseRequisition.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(status, requested_by),
    )
