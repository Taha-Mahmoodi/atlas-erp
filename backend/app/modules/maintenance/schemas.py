"""Maintenance request/response schemas (Pydantic v2, ApiModel base) for PLAN 9.2.

Create/Update/Read/Filter for the three entities (Equipment, MaintenanceOrder, MaintenancePlan) plus
the order action payloads (schedule / complete / cancel via path only) and the preventive run. Money
amounts are ``Decimal`` strings (D-015); a ``code`` is immutable so it is absent from the Update
schemas (the work-centre precedent). The Read schemas carry the server-derived fields (number,
status, computed next_due_date, timestamps).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.core.schemas import ApiModel
from app.modules.maintenance.constants import (
    EquipmentStatus,
    IntervalUnit,
    MaintenanceOrderStatus,
    MaintenanceOrderType,
    MaintenancePlanStatus,
)

# --- Equipment ----------------------------------------------------------------


class EquipmentCreate(ApiModel):
    """Create a piece of equipment. ``code`` is user-supplied + unique per tenant;
    ``cost_center_id`` (optional) is validated to exist in finance when set (D-029)."""

    code: str
    name: str
    description: str | None = None
    status: EquipmentStatus = EquipmentStatus.ACTIVE
    location: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    commissioned_date: date | None = None
    cost_center_id: uuid.UUID | None = None
    notes: str | None = None


class EquipmentUpdate(ApiModel):
    """Partial update. ``code`` is immutable (absent here); a changed ``cost_center_id`` is
    re-validated. All fields optional — only the set ones change (exclude_unset)."""

    name: str | None = None
    description: str | None = None
    status: EquipmentStatus | None = None
    location: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    commissioned_date: date | None = None
    cost_center_id: uuid.UUID | None = None
    notes: str | None = None


class EquipmentRead(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    status: EquipmentStatus
    location: str | None
    manufacturer: str | None
    model: str | None
    serial_number: str | None
    commissioned_date: date | None
    cost_center_id: uuid.UUID | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class EquipmentFilter(ApiModel):
    """List filters. None means "no constraint"; folded into the cursor's filter fingerprint so a
    cursor cannot cross filtered views."""

    status: EquipmentStatus | None = None


# --- Maintenance order --------------------------------------------------------


class MaintenanceOrderCreate(ApiModel):
    """Create a CORRECTIVE maintenance order (ad-hoc). The equipment must exist and be ACTIVE.
    ``scheduled_date`` makes it SCHEDULED at creation; omitting it leaves it DRAFT. PREVENTIVE
    orders are NOT created via this schema — they come from a plan's run. ``order_type`` is
    therefore not a field (always CORRECTIVE here)."""

    equipment_id: uuid.UUID
    description: str
    scheduled_date: date | None = None
    estimated_cost: Decimal | None = None
    assigned_to: uuid.UUID | None = None
    notes: str | None = None


class MaintenanceOrderUpdate(ApiModel):
    """Partial update of a non-terminal order's editable fields (description / estimate / assignee /
    notes). The status is changed via the schedule/start/complete/cancel actions, not here."""

    description: str | None = None
    estimated_cost: Decimal | None = None
    assigned_to: uuid.UUID | None = None
    notes: str | None = None


class MaintenanceOrderRead(ApiModel):
    id: uuid.UUID
    order_number: str
    order_type: MaintenanceOrderType
    status: MaintenanceOrderStatus
    equipment_id: uuid.UUID
    maintenance_plan_id: uuid.UUID | None
    description: str
    scheduled_date: date
    completed_date: date | None
    estimated_cost: Decimal | None
    actual_cost: Decimal | None
    assigned_to: uuid.UUID | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class MaintenanceOrderFilter(ApiModel):
    equipment_id: uuid.UUID | None = None
    order_type: MaintenanceOrderType | None = None
    status: MaintenanceOrderStatus | None = None


class ScheduleOrderRequest(ApiModel):
    """Schedule a DRAFT order (→ SCHEDULED) on a planned date."""

    scheduled_date: date


class CompleteOrderRequest(ApiModel):
    """Complete an order (→ COMPLETED): record the ``actual_cost`` (record-only, no GL, D-051) and
    an optional completion date (defaults to today)."""

    actual_cost: Decimal | None = None
    completed_date: date | None = None


# --- Maintenance plan ---------------------------------------------------------


class MaintenancePlanCreate(ApiModel):
    """Create an interval-based preventive plan. ``code`` is user-supplied + unique;
    ``equipment_id`` must exist; ``interval_value`` > 0. ``start_date`` seeds the first
    ``next_due_date`` (defaults to today + one interval if omitted — the first task is one interval
    out)."""

    code: str
    name: str
    equipment_id: uuid.UUID
    interval_value: int
    interval_unit: IntervalUnit
    task_description: str
    start_date: date | None = None
    estimated_cost: Decimal | None = None


class MaintenancePlanUpdate(ApiModel):
    """Partial update. ``code`` and ``equipment_id`` are immutable (absent here). A changed interval
    does NOT retro-shift the existing ``next_due_date`` (it applies to the NEXT advance — documented
    in the service)."""

    name: str | None = None
    interval_value: int | None = None
    interval_unit: IntervalUnit | None = None
    task_description: str | None = None
    estimated_cost: Decimal | None = None


class MaintenancePlanRead(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    equipment_id: uuid.UUID
    status: MaintenancePlanStatus
    interval_value: int
    interval_unit: IntervalUnit
    task_description: str
    last_generated_date: date | None
    next_due_date: date
    estimated_cost: Decimal | None
    created_at: datetime
    updated_at: datetime


class MaintenancePlanFilter(ApiModel):
    status: MaintenancePlanStatus | None = None
    equipment_id: uuid.UUID | None = None


class RunPreventiveResult(ApiModel):
    """The outcome of one preventive-generation run (PLAN 9.2): how many plans were due and the
    orders generated (one per due plan), with the as-of date the run used."""

    as_of_date: date
    plans_due: int
    orders_generated: list[MaintenanceOrderRead]
