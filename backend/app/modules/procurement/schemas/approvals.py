"""Approval-rule schemas (Pydantic v2, ApiModel base) for PLAN 6.2.

Create/Update/Read/Filter for the value-threshold rule (D-040). ``threshold_amount`` is a plain
``Decimal`` (>= 0, D-015). ``document_type`` is REQUISITION or PURCHASE_ORDER; one rule per
(tenant, document_type) so Create rejects a second rule for the same type at the service.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.core.schemas import ApiModel
from app.modules.procurement.constants import ApprovalDocumentType


class ApprovalRuleCreate(ApiModel):
    """Create a value-threshold approval rule (PLAN 6.2). One rule per (tenant, document_type) —
    a second create for the same document_type is a friendly ConflictError."""

    document_type: ApprovalDocumentType
    threshold_amount: Decimal = Field(ge=0)
    currency_code: str = Field(min_length=3, max_length=3)
    is_active: bool = True
    description: str | None = None


class ApprovalRuleUpdate(ApiModel):
    """Partial update — every field optional. ``document_type`` is immutable (it keys the rule) and
    so is absent. A changed ``threshold_amount`` must stay >= 0; ``is_active`` toggles the rule."""

    threshold_amount: Decimal | None = Field(default=None, ge=0)
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    is_active: bool | None = None
    description: str | None = None


class ApprovalRuleRead(ApiModel):
    id: uuid.UUID
    document_type: ApprovalDocumentType
    threshold_amount: Decimal
    currency_code: str
    is_active: bool
    description: str | None
    created_at: datetime
    updated_at: datetime


class ApprovalRuleFilter(ApiModel):
    """List filters: by document type and/or active flag."""

    document_type: ApprovalDocumentType | None = None
    is_active: bool | None = None
