"""Maintenance-plan business logic (PLAN 9.2, D-051): CRUD + activate/deactivate + the preventive
generation RUN.

A plan defines a recurring preventive task on a piece of equipment. The RUN scans the tenant's
ACTIVE plans whose ``next_due_date`` has arrived (set-based, via ``queries.due_plans`` — PERFORMANCE
§2) and creates ONE PREVENTIVE maintenance order per due plan, then advances the plan.

THE OVERDUE-ADVANCE RULE (D-051). A plan overdue by MULTIPLE intervals generates exactly ONE order
(scheduled at its current ``next_due_date``) and advances ``next_due_date`` forward by whole
intervals until it is strictly AFTER the run's ``as_of`` (generate-one-advance-to-next-future). This
avoids order spam when a plan was missed for several cycles while keeping the schedule on cadence.

IDEMPOTENT (D-051). After a plan generates, its ``next_due_date`` is strictly > ``as_of``, so a
re-run of the generator the same day finds it not-due and generates nothing.

The plan is a docflow PREDECESSOR of the orders it spawns: it registers a document at creation, and
the run writes a plan→'generates'→order edge per generated order.

``from __future__ import annotations`` keeps ``Page[MaintenancePlan]`` a string at import.
"""

from __future__ import annotations

import calendar
import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.maintenance import queries as maintenance_queries
from app.modules.maintenance.constants import (
    MAINTENANCE_PLAN_DOC_TYPE,
    PLAN_GENERATES_ORDER_LINK,
    IntervalUnit,
    MaintenancePlanStatus,
)
from app.modules.maintenance.models import MaintenanceOrder, MaintenancePlan
from app.modules.maintenance.schemas import (
    MaintenancePlanCreate,
    MaintenancePlanUpdate,
)
from app.modules.maintenance.service.equipment import get_equipment
from app.modules.maintenance.service.orders import create_generated_order


def _add_months(anchor: date, months: int) -> date:
    """``anchor`` shifted forward by ``months`` calendar months, clamped to the target month's last
    valid day (so 2026-01-31 + 1 month = 2026-02-28). The finance periods._add_months pattern —
    re-declared here (a private service helper is not imported across modules)."""
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(anchor.day, last_day))


def advance_due_date(anchor: date, interval_value: int, interval_unit: IntervalUnit) -> date:
    """``anchor`` advanced by ONE interval (D-051). DAYS/WEEKS use timedelta; MONTHS uses calendar
    arithmetic (end-of-month clamped)."""
    unit = IntervalUnit(interval_unit)
    if unit == IntervalUnit.DAYS:
        return anchor + timedelta(days=interval_value)
    if unit == IntervalUnit.WEEKS:
        return anchor + timedelta(weeks=interval_value)
    return _add_months(anchor, interval_value)


async def get_maintenance_plan(
    session: AsyncSession, tenant_id: uuid.UUID, plan_id: uuid.UUID
) -> MaintenancePlan:
    plan = await session.get(MaintenancePlan, plan_id)
    if plan is None or plan.tenant_id != tenant_id:
        raise NotFoundError(
            message="Maintenance plan not found", code="maintenance.plan_not_found"
        )
    return plan


async def create_plan(
    session: AsyncSession, tenant_id: uuid.UUID, payload: MaintenancePlanCreate
) -> MaintenancePlan:
    """Create an interval-based preventive plan (D-051). Rejects a duplicate code; validates the
    equipment exists and ``interval_value`` > 0; computes the first ``next_due_date`` as
    ``start_date`` (or today) + one interval. Registers a plan document so the plan can be the
    docflow predecessor of the orders it generates. Born ACTIVE."""
    if payload.interval_value <= 0:
        raise ValidationFailedError(
            message="The plan interval must be greater than zero",
            code="maintenance.interval_invalid",
            details={"interval_value": payload.interval_value},
        )
    existing = (
        await session.execute(
            select(MaintenancePlan.id).where(
                MaintenancePlan.tenant_id == tenant_id,
                MaintenancePlan.code == payload.code,
            )
        )
    ).first()
    if existing is not None:
        raise ConflictError(
            message=f"A maintenance plan with code {payload.code} already exists",
            code="maintenance.plan_code_conflict",
            details={"code": payload.code},
        )
    # Validate the equipment exists (an opaque-feeling but intra-module reference — load it so a 404
    # surfaces as a clean validation error).
    await get_equipment(session, tenant_id, payload.equipment_id)

    start = payload.start_date or date.today()
    next_due = advance_due_date(start, payload.interval_value, payload.interval_unit)

    plan_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        MAINTENANCE_PLAN_DOC_TYPE,
        plan_id,
        doc_number=None,
        status=MaintenancePlanStatus.ACTIVE.value,
    )
    plan = MaintenancePlan(
        id=plan_id,
        tenant_id=tenant_id,
        document_id=document.id,
        code=payload.code,
        name=payload.name,
        equipment_id=payload.equipment_id,
        status=MaintenancePlanStatus.ACTIVE.value,
        interval_value=payload.interval_value,
        # ApiModel sets use_enum_values=True, so payload.interval_unit is already its string value.
        interval_unit=payload.interval_unit,
        task_description=payload.task_description,
        last_generated_date=None,
        next_due_date=next_due,
        estimated_cost=payload.estimated_cost,
    )
    session.add(plan)
    await session.flush()
    return plan


async def update_plan(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    plan_id: uuid.UUID,
    payload: MaintenancePlanUpdate,
) -> MaintenancePlan:
    """Partial update (D-010: mutate the loaded object). ``code`` and ``equipment_id`` are immutable
    (absent from the schema). A changed interval applies to the NEXT advance — it does NOT
    retro-shift the current ``next_due_date`` (D-051). ``interval_value`` > 0 is re-validated when
    set."""
    plan = await get_maintenance_plan(session, tenant_id, plan_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("interval_value") is not None and data["interval_value"] <= 0:
        raise ValidationFailedError(
            message="The plan interval must be greater than zero",
            code="maintenance.interval_invalid",
            details={"interval_value": data["interval_value"]},
        )
    # ApiModel sets use_enum_values=True, so a dumped interval_unit is already its string value.
    for field, value in data.items():
        setattr(plan, field, value)
    await session.flush()
    return plan


async def set_plan_status(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    plan_id: uuid.UUID,
    new_status: MaintenancePlanStatus,
) -> MaintenancePlan:
    """Activate/deactivate a plan (D-051): an INACTIVE plan is skipped by the generation run.
    Idempotent (setting the current status is a no-op)."""
    plan = await get_maintenance_plan(session, tenant_id, plan_id)
    plan.status = new_status.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, plan.document_id, status=new_status.value
    )
    return plan


async def list_plans(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    status: MaintenancePlanStatus | None = None,
    equipment_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[MaintenancePlan]:
    """Keyset-paginated plans ordered by code (D-014). The status/equipment filters narrow the set
    and fold into the cursor fingerprint."""
    stmt = select(MaintenancePlan).where(MaintenancePlan.tenant_id == tenant_id)
    if status is not None:
        stmt = stmt.where(MaintenancePlan.status == status.value)
    if equipment_id is not None:
        stmt = stmt.where(MaintenancePlan.equipment_id == equipment_id)
    fingerprint = filter_fingerprint(status, equipment_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(MaintenancePlan.code, SortDirection.ASC)],
        pk=MaintenancePlan.id,
        cursor=cursor,
        limit=limit,
        filters=fingerprint,
    )


def _next_future_due(plan: MaintenancePlan, as_of: date) -> date:
    """Advance the plan's ``next_due_date`` by whole intervals until it is strictly AFTER ``as_of``
    (the OVERDUE-ADVANCE rule, D-051). At least one advance always runs (the plan was due, so its
    current next_due_date <= as_of)."""
    due = plan.next_due_date
    unit = IntervalUnit(plan.interval_unit)
    while due <= as_of:
        due = advance_due_date(due, plan.interval_value, unit)
    return due


async def run_preventive_maintenance(
    session: AsyncSession, tenant_id: uuid.UUID, as_of_date: date
) -> list[MaintenanceOrder]:
    """Generate PREVENTIVE orders for every ACTIVE plan due on/before ``as_of_date`` (D-051).

    Set-based scan (``queries.due_plans`` — ONE query, PERFORMANCE §2). Per due plan: create ONE
    PREVENTIVE order scheduled at the plan's CURRENT ``next_due_date``, write the plan→'generates'→
    order docflow edge, set ``last_generated_date`` = that due date, and advance ``next_due_date``
    to the next FUTURE due date (overdue-advance rule — one order even when overdue by several
    intervals). Idempotent: after the advance ``next_due_date`` > ``as_of``, so a same-day re-run
    generates nothing. Returns the created orders. The caller commits via uow (D-011).
    """
    due = await maintenance_queries.due_plans(session, tenant_id, as_of_date)
    generated: list[MaintenanceOrder] = []
    for plan in due:
        scheduled_date = plan.next_due_date
        order = await create_generated_order(
            session,
            tenant_id,
            equipment_id=plan.equipment_id,
            maintenance_plan_id=plan.id,
            description=plan.task_description,
            scheduled_date=scheduled_date,
            estimated_cost=plan.estimated_cost,
        )
        await docflow.link_documents(
            session,
            tenant_id,
            plan.document_id,
            order.document_id,
            link_type=PLAN_GENERATES_ORDER_LINK,
        )
        plan.last_generated_date = scheduled_date
        plan.next_due_date = _next_future_due(plan, as_of_date)
        generated.append(order)
    await session.flush()
    return generated
