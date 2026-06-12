"""Controlling request/response schemas (PLAN 4.7, Pydantic v2 ApiModel base).

Read schemas mirror the controlling models field-for-field in snake_case; enums are typed with the
constants classes (ApiModel's ``use_enum_values`` serializes them as their UPPER_SNAKE string). A
separate file from ``schemas.py`` because that file is at the STRUCTURE §3 size cap — the same split
``payables_schemas.py`` / ``receivables_schemas.py`` use. ``weight`` and ``allocated_amount`` are
Decimal, serialized as strings (D-015).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.core.schemas import ApiModel
from app.modules.finance.constants import AllocationBasis, AllocationRunStatus

# --- Cost centers -------------------------------------------------------------


class CostCenterCreate(ApiModel):
    code: str
    name: str
    parent_id: uuid.UUID | None = None
    is_active: bool = True
    manager_name: str | None = None
    default_profit_center_id: uuid.UUID | None = None


class CostCenterUpdate(ApiModel):
    """Partial update — every field optional; ``code`` is immutable (posted journal lines carry the
    id, not the code, but keeping the code stable matches the rest of finance's master data)."""

    name: str | None = None
    parent_id: uuid.UUID | None = None
    is_active: bool | None = None
    manager_name: str | None = None
    default_profit_center_id: uuid.UUID | None = None


class CostCenterRead(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    parent_id: uuid.UUID | None
    is_active: bool
    manager_name: str | None
    default_profit_center_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


# --- Profit centers -----------------------------------------------------------


class ProfitCenterCreate(ApiModel):
    code: str
    name: str
    parent_id: uuid.UUID | None = None
    is_active: bool = True


class ProfitCenterUpdate(ApiModel):
    name: str | None = None
    parent_id: uuid.UUID | None = None
    is_active: bool | None = None


class ProfitCenterRead(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    parent_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


# --- Allocation rules + targets -----------------------------------------------


class AllocationTargetCreate(ApiModel):
    """One target of an allocation rule. ``weight`` is a percent (PERCENT basis — the rule's targets
    must sum to 100) or an arbitrary positive fixed weight (FIXED_WEIGHT basis — proportional)."""

    target_cost_center_id: uuid.UUID
    weight: Decimal


class AllocationRuleCreate(ApiModel):
    """Create an allocation rule with its targets. PERCENT weights must sum to 100; FIXED_WEIGHT
    weights are any positive numbers (the service validates). The source must differ from every
    target (a cost centre cannot allocate to itself)."""

    code: str
    name: str
    source_cost_center_id: uuid.UUID
    basis: AllocationBasis = AllocationBasis.PERCENT
    is_active: bool = True
    targets: list[AllocationTargetCreate]


class AllocationRuleUpdate(ApiModel):
    """Partial update of a rule's header + (optionally) its full target set. When ``targets`` is
    supplied it REPLACES the rule's targets atomically (re-validated against the basis)."""

    name: str | None = None
    basis: AllocationBasis | None = None
    is_active: bool | None = None
    targets: list[AllocationTargetCreate] | None = None


class AllocationTargetRead(ApiModel):
    id: uuid.UUID
    target_cost_center_id: uuid.UUID
    weight: Decimal


class AllocationRuleRead(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    source_cost_center_id: uuid.UUID
    basis: AllocationBasis
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AllocationRuleDetail(AllocationRuleRead):
    """A rule WITH its targets — the GET /{id} shape."""

    targets: list[AllocationTargetRead]


# --- Allocation runs ----------------------------------------------------------


class AllocationRunRequest(ApiModel):
    """Run an allocation rule for a fiscal period. ``run_date`` dates the posted journal entry (must
    fall in an open period); the source cost centre's net balance for ``fiscal_period_id`` is the
    amount distributed to the targets."""

    allocation_rule_id: uuid.UUID
    fiscal_period_id: uuid.UUID
    run_date: date


class AllocationRunRead(ApiModel):
    id: uuid.UUID
    allocation_rule_id: uuid.UUID
    fiscal_period_id: uuid.UUID
    run_number: str | None
    run_date: date
    allocated_amount: Decimal
    journal_entry_id: uuid.UUID | None
    status: AllocationRunStatus
    created_at: datetime
    updated_at: datetime
