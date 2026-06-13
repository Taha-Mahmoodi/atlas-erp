"""Purchase-requisition schemas (Pydantic v2, ApiModel base) for PLAN 6.2.

Header + line Create/Update/Read/Detail/Filter plus the action payloads (submit, approve/reject).
Money/quantity are plain ``Decimal`` (the finance schema precedent — exact on both engines via the
MoneyType/QuantityType columns, D-015). ``status`` is typed with the ``RequisitionStatus`` constant
(ApiModel ``use_enum_values`` serializes the UPPER_SNAKE string). Server-owned fields (id, number,
status, timestamps) are absent from Create/Update.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.core.schemas import ApiModel
from app.modules.procurement.constants import ApprovalDecision, RequisitionStatus


class RequisitionLineCreate(ApiModel):
    """One requested line. ``item_id`` / ``uom_id`` are opaque inventory ids (validated to exist,
    D-029); ``quantity`` must be > 0 (the service enforces it). ``estimated_unit_cost`` is the
    requester's optional budgetary estimate."""

    item_id: uuid.UUID
    description: str | None = None
    quantity: Decimal
    uom_id: uuid.UUID
    estimated_unit_cost: Decimal | None = None
    currency_code: str


class RequisitionCreate(ApiModel):
    """Create a DRAFT requisition (PLAN 6.2). At least one line is required; the service claims the
    PR number, validates every item exists and qty > 0, and registers the document."""

    requested_by: uuid.UUID | None = None
    needed_by_date: date | None = None
    notes: str | None = None
    lines: list[RequisitionLineCreate]


class RequisitionUpdate(ApiModel):
    """Partial update of a DRAFT requisition's header (PLAN 6.2). Lines are replaced wholesale when
    ``lines`` is supplied (the simplest correct edit for a draft — the service revalidates them).
    A non-draft requisition cannot be updated (the service rejects it)."""

    requested_by: uuid.UUID | None = None
    needed_by_date: date | None = None
    notes: str | None = None
    lines: list[RequisitionLineCreate] | None = None


class RequisitionLineRead(ApiModel):
    id: uuid.UUID
    line_number: int
    item_id: uuid.UUID
    description: str | None
    quantity: Decimal
    uom_id: uuid.UUID
    estimated_unit_cost: Decimal | None
    currency_code: str


class RequisitionRead(ApiModel):
    """Requisition header without lines — the list-row shape."""

    id: uuid.UUID
    requisition_number: str
    status: RequisitionStatus
    requested_by: uuid.UUID | None
    needed_by_date: date | None
    notes: str | None
    document_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class RequisitionDetail(RequisitionRead):
    """Requisition header WITH its lines — the GET /{id} shape."""

    lines: list[RequisitionLineRead]


class RequisitionFilter(ApiModel):
    """List filters: by status and/or requesting user. None means no constraint (folds into the
    cursor fingerprint so a cursor cannot cross filtered views)."""

    status: RequisitionStatus | None = None
    requested_by: uuid.UUID | None = None


class ApprovalDecisionPayload(ApiModel):
    """An approver's verdict on a submitted requisition or pending PO (the approve/reject action).
    ``decision`` is APPROVED or REJECTED; ``comment`` is an optional note recorded in the audit
    trail via the status change."""

    decision: ApprovalDecision
    comment: str | None = None
