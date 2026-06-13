"""Work-centre business logic (PLAN 8.1): CRUD + cost-centre validation.

The service layer owns every rule (CLAUDE.md rule 7); the router stays thin. The optional
``cost_center_id`` is an OPAQUE finance cost-centre id (D-029): validated to exist via
``finance/queries.cost_center_exists`` (the sanctioned cross-module read, STRUCTURE §5) — never a
cross-module FK. ``from __future__ import annotations`` keeps ``Page[WorkCenter]`` (the ORM model) a
string at import; the router re-validates page items.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.finance import queries as finance_queries
from app.modules.manufacturing.models import WorkCenter
from app.modules.manufacturing.schemas import (
    WorkCenterCreate,
    WorkCenterFilter,
    WorkCenterUpdate,
)


async def _validate_cost_center(
    session: AsyncSession, tenant_id: uuid.UUID, cost_center_id: uuid.UUID | None
) -> None:
    """A supplied cost-centre id must exist in finance (D-029): validated via the finance queries
    contract, never a cross-module FK. None is skipped (the cost centre is optional)."""
    if cost_center_id is None:
        return
    if not await finance_queries.cost_center_exists(session, tenant_id, cost_center_id):
        raise ValidationFailedError(
            message="Referenced cost centre does not exist",
            code="manufacturing.cost_center_not_found",
            details={"cost_center_id": str(cost_center_id)},
        )


async def get_work_center(
    session: AsyncSession, tenant_id: uuid.UUID, work_center_id: uuid.UUID
) -> WorkCenter:
    work_center = await session.get(WorkCenter, work_center_id)
    if work_center is None or work_center.tenant_id != tenant_id:
        raise NotFoundError(
            message="Work centre not found", code="manufacturing.work_center_not_found"
        )
    return work_center


async def create_work_center(
    session: AsyncSession, tenant_id: uuid.UUID, payload: WorkCenterCreate
) -> WorkCenter:
    """Create a work centre. Rejects a duplicate code (the DB UNIQUE is the backstop); validates the
    cost centre exists in finance when set."""
    existing = (
        await session.execute(
            select(WorkCenter.id).where(
                WorkCenter.tenant_id == tenant_id, WorkCenter.code == payload.code
            )
        )
    ).first()
    if existing is not None:
        raise ConflictError(
            message=f"A work centre with code {payload.code} already exists",
            code="manufacturing.work_center_code_conflict",
            details={"code": payload.code},
        )
    await _validate_cost_center(session, tenant_id, payload.cost_center_id)
    work_center = WorkCenter(
        tenant_id=tenant_id,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        cost_center_id=payload.cost_center_id,
        capacity_hours_per_day=payload.capacity_hours_per_day,
        efficiency_percent=payload.efficiency_percent,
        is_active=payload.is_active,
    )
    session.add(work_center)
    await session.flush()
    return work_center


async def update_work_center(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    work_center_id: uuid.UUID,
    payload: WorkCenterUpdate,
) -> WorkCenter:
    """Partial update (D-010: mutate the loaded object so the audit diff is captured). ``code`` is
    immutable and absent from the schema; a changed cost centre is re-validated."""
    work_center = await get_work_center(session, tenant_id, work_center_id)
    data = payload.model_dump(exclude_unset=True)
    if "cost_center_id" in data:
        await _validate_cost_center(session, tenant_id, data["cost_center_id"])
    for field, value in data.items():
        setattr(work_center, field, value)
    await session.flush()
    return work_center


async def list_work_centers(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    filters: WorkCenterFilter,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[WorkCenter]:
    """Keyset-paginated work centres ordered by code (D-014). The active filter narrows the set and
    folds into the cursor fingerprint so a cursor cannot bleed across views."""
    stmt = select(WorkCenter).where(WorkCenter.tenant_id == tenant_id)
    if filters.is_active is not None:
        stmt = stmt.where(WorkCenter.is_active == filters.is_active)
    fingerprint = filter_fingerprint(filters.is_active)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(WorkCenter.code, SortDirection.ASC)],
        pk=WorkCenter.id,
        cursor=cursor,
        limit=limit,
        filters=fingerprint,
    )
