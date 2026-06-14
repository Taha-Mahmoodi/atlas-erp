"""Activity business logic (PLAN 12.1, D-057): activity CRUD against a lead OR an opportunity, with
the EXACTLY-ONE-PARENT rule, and complete/cancel.

The service layer owns every rule (CLAUDE.md rule 7); the router stays thin. THE HEADLINE RULE: an
activity is logged against EXACTLY ONE of a lead or an opportunity — the service validates exactly
one
of ``lead_id`` / ``opportunity_id`` is set AND that the named parent exists (a friendly 422 up
front),
and the ``ck_crm_activities_one_parent`` DB CHECK is the bypass-proof backstop.
``complete``/``cancel``
are the status transitions (OPEN → COMPLETED/CANCELLED). An activity claims no number (it is a child
of
its parent, not a numbered document).

``from __future__ import annotations`` keeps ``Page[Activity]`` a string at import.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.crm import queries as crm_queries
from app.modules.crm.constants import ActivityStatus
from app.modules.crm.models import Activity
from app.modules.crm.schemas import ActivityCreate, ActivityFilter, ActivityUpdate
from app.modules.crm.service._shared import validate_owner


async def get_activity(
    session: AsyncSession, tenant_id: uuid.UUID, activity_id: uuid.UUID
) -> Activity:
    activity = await session.get(Activity, activity_id)
    if activity is None or activity.tenant_id != tenant_id:
        raise NotFoundError(message="Activity not found", code="crm.activity_not_found")
    return activity


async def _validate_parent(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    lead_id: uuid.UUID | None,
    opportunity_id: uuid.UUID | None,
) -> None:
    """EXACTLY-ONE-PARENT (D-057): exactly one of ``lead_id`` / ``opportunity_id`` must be set, and
    the
    named parent must exist in the tenant. Rejects zero parents, both parents, or an unknown parent
    with a friendly 422 (the DB CHECK is the backstop for the zero/both cases)."""
    if (lead_id is None) == (opportunity_id is None):
        raise ValidationFailedError(
            message="An activity must reference exactly one of a lead or an opportunity",
            code="crm.activity_parent_invalid",
        )
    if lead_id is not None and not await crm_queries.lead_exists(session, tenant_id, lead_id):
        raise ValidationFailedError(
            message="Referenced lead does not exist",
            code="crm.lead_not_found",
            details={"lead_id": str(lead_id)},
        )
    if opportunity_id is not None and not await crm_queries.opportunity_exists(
        session, tenant_id, opportunity_id
    ):
        raise ValidationFailedError(
            message="Referenced opportunity does not exist",
            code="crm.opportunity_not_found",
            details={"opportunity_id": str(opportunity_id)},
        )


async def create_activity(
    session: AsyncSession, tenant_id: uuid.UUID, payload: ActivityCreate
) -> Activity:
    """Create an activity against exactly one parent (PLAN 12.1). Validates exactly-one-parent + the
    parent exists, and the owner (if set) exists in hr. ``status`` defaults to OPEN; a COMPLETED
    activity created directly stamps today as the completed date (a recorded-fact NOTE)."""
    await _validate_parent(session, tenant_id, payload.lead_id, payload.opportunity_id)
    await validate_owner(session, tenant_id, payload.owner_employee_id)
    completed_date = (
        date.today() if ActivityStatus(payload.status) == ActivityStatus.COMPLETED else None
    )
    activity = Activity(
        tenant_id=tenant_id,
        # ApiModel use_enum_values=True, so the payload enums are already string values.
        activity_type=payload.activity_type,
        status=payload.status,
        subject=payload.subject,
        description=payload.description,
        due_date=payload.due_date,
        completed_date=completed_date,
        lead_id=payload.lead_id,
        opportunity_id=payload.opportunity_id,
        owner_employee_id=payload.owner_employee_id,
    )
    session.add(activity)
    await session.flush()
    return activity


async def update_activity(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    activity_id: uuid.UUID,
    payload: ActivityUpdate,
) -> Activity:
    """Partial update of an OPEN activity (D-010: mutate the loaded object). The parent is immutable
    (absent from the schema) and the status moves via complete/cancel. A terminal
    (COMPLETED/CANCELLED)
    activity is immutable. A changed owner is re-validated."""
    activity = await get_activity(session, tenant_id, activity_id)
    if ActivityStatus(activity.status) != ActivityStatus.OPEN:
        raise ConflictError(
            message="A completed or cancelled activity cannot be edited",
            code="crm.activity_not_open",
            details={"status": activity.status},
        )
    data = payload.model_dump(exclude_unset=True)
    if "owner_employee_id" in data:
        await validate_owner(session, tenant_id, data["owner_employee_id"])
    for field, value in data.items():
        setattr(activity, field, value)
    await session.flush()
    return activity


async def complete_activity(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    activity_id: uuid.UUID,
    *,
    completed_date: date | None = None,
) -> Activity:
    """Complete an OPEN activity (PLAN 12.1): OPEN → COMPLETED, stamping ``completed_date``
    (defaults
    to today). Only an OPEN activity can be completed."""
    activity = await get_activity(session, tenant_id, activity_id)
    if ActivityStatus(activity.status) != ActivityStatus.OPEN:
        raise ConflictError(
            message="Only an open activity can be completed",
            code="crm.activity_not_completable",
            details={"status": activity.status},
        )
    activity.status = ActivityStatus.COMPLETED.value
    activity.completed_date = completed_date or date.today()
    await session.flush()
    return activity


async def cancel_activity(
    session: AsyncSession, tenant_id: uuid.UUID, activity_id: uuid.UUID
) -> Activity:
    """Cancel an OPEN activity (PLAN 12.1): OPEN → CANCELLED. Only an OPEN activity can be cancelled
    (a completed one is a recorded fact)."""
    activity = await get_activity(session, tenant_id, activity_id)
    if ActivityStatus(activity.status) != ActivityStatus.OPEN:
        raise ConflictError(
            message="Only an open activity can be cancelled",
            code="crm.activity_not_cancellable",
            details={"status": activity.status},
        )
    activity.status = ActivityStatus.CANCELLED.value
    await session.flush()
    return activity


async def list_activities(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    filters: ActivityFilter,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[Activity]:
    """Keyset-paginated activities, newest first (D-014). The status + lead/opportunity filters
    narrow
    the set (index-served by (tenant, lead_id) / (tenant, opportunity_id) / (tenant, status)) and
    fold
    into the cursor fingerprint."""
    stmt = select(Activity).where(Activity.tenant_id == tenant_id)
    if filters.status is not None:
        stmt = stmt.where(Activity.status == ActivityStatus(filters.status).value)
    if filters.lead_id is not None:
        stmt = stmt.where(Activity.lead_id == filters.lead_id)
    if filters.opportunity_id is not None:
        stmt = stmt.where(Activity.opportunity_id == filters.opportunity_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(Activity.created_at, SortDirection.DESC)],
        pk=Activity.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(filters.status, filters.lead_id, filters.opportunity_id),
    )
