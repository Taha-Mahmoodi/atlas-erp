"""MRP request/response schemas (Pydantic v2, ApiModel base) for PLAN 8.3.

An MRP RUN is submitted as a background job (the endpoint returns 202 ``JobSubmitted``); the run +
its planned orders + capacity loads are then read back. ``status`` fields are server-driven.
Quantities/minutes are ``Decimal`` strings (D-015). The run request carries the optional planning
date / horizon / warehouse scope; everything else is server-derived.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.core.schemas import ApiModel
from app.modules.manufacturing.constants import (
    MrpRunStatus,
    PlannedOrderStatus,
    PlannedOrderType,
)


class MrpRunRequest(ApiModel):
    """Run MRP (D-049). ``run_date`` defaults to today (the planning date the net plan is dated on);
    ``horizon_days`` is the netting/capacity window (defaults to the module default);
    ``warehouse_id`` is reserved for a warehouse-scoped run — v1 MRP is TENANT-WIDE, so it is
    OPTIONAL and only recorded on the run (parity: MRP areas / multi-plant deferred)."""

    run_date: date | None = None
    horizon_days: int | None = None
    warehouse_id: uuid.UUID | None = None


class MrpRunRead(ApiModel):
    id: uuid.UUID
    run_number: str
    status: MrpRunStatus
    run_date: date
    horizon_days: int
    warehouse_id: uuid.UUID | None
    demand_source: str | None
    planned_make_count: int
    planned_buy_count: int
    notes: str | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PlannedOrderRead(ApiModel):
    id: uuid.UUID
    mrp_run_id: uuid.UUID
    item_id: uuid.UUID
    order_type: PlannedOrderType
    quantity: Decimal
    due_date: date | None
    status: PlannedOrderStatus
    source_notes: str | None
    level: int
    converted_document_id: uuid.UUID | None
    created_at: datetime


class CapacityLoadRead(ApiModel):
    id: uuid.UUID
    mrp_run_id: uuid.UUID
    work_center_id: uuid.UUID
    planned_load_minutes: Decimal
    available_minutes: Decimal
    utilization_percent: Decimal
    is_overloaded: bool


class MrpRunSummary(MrpRunRead):
    """A run header plus its capacity loads (the GET {id} summary) — the planned orders are
    paginated separately (a run can produce many)."""

    capacity_loads: list[CapacityLoadRead]


class PlannedOrderConvertRequest(ApiModel):
    """Convert a planned order (D-049). ``warehouse_id`` is required for a MAKE order whose run had
    no warehouse scope (a production order must issue/finish somewhere); ignored for BUY (the
    requisition has no warehouse)."""

    warehouse_id: uuid.UUID | None = None
