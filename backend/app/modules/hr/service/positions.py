"""Position business logic (PLAN 10.1, D-052): CRUD + department validation.

The service layer owns every rule (CLAUDE.md rule 7); the router stays thin. A position's optional
``department_id`` must reference an existing department in the tenant (an intra-module read via
``hr/queries.get_department``). ``code`` is immutable. ``from __future__ import annotations`` keeps
``Page[Position]`` a string at import; the router re-validates page items.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.hr import queries as hr_queries
from app.modules.hr.models import Position
from app.modules.hr.schemas import PositionCreate, PositionFilter, PositionUpdate


async def _validate_department(
    session: AsyncSession, tenant_id: uuid.UUID, department_id: uuid.UUID | None
) -> None:
    """A supplied department must exist in the tenant (D-052). None is skipped (a position may be
    unassigned)."""
    if department_id is None:
        return
    if await hr_queries.get_department(session, tenant_id, department_id) is None:
        raise ValidationFailedError(
            message="Referenced department does not exist",
            code="hr.department_not_found",
            details={"department_id": str(department_id)},
        )


async def get_position(
    session: AsyncSession, tenant_id: uuid.UUID, position_id: uuid.UUID
) -> Position:
    position = await session.get(Position, position_id)
    if position is None or position.tenant_id != tenant_id:
        raise NotFoundError(message="Position not found", code="hr.position_not_found")
    return position


async def create_position(
    session: AsyncSession, tenant_id: uuid.UUID, payload: PositionCreate
) -> Position:
    """Create a position. Rejects a duplicate code; validates the department when set."""
    existing = (
        await session.execute(
            select(Position.id).where(
                Position.tenant_id == tenant_id, Position.code == payload.code
            )
        )
    ).first()
    if existing is not None:
        raise ConflictError(
            message=f"Position with code {payload.code} already exists",
            code="hr.position_code_conflict",
            details={"code": payload.code},
        )
    await _validate_department(session, tenant_id, payload.department_id)
    position = Position(
        tenant_id=tenant_id,
        code=payload.code,
        title=payload.title,
        description=payload.description,
        department_id=payload.department_id,
        is_active=payload.is_active,
    )
    session.add(position)
    await session.flush()
    return position


async def update_position(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    position_id: uuid.UUID,
    payload: PositionUpdate,
) -> Position:
    """Partial update (D-010: mutate the loaded object so the audit diff is captured). ``code`` is
    immutable and absent; a changed department is re-validated."""
    position = await get_position(session, tenant_id, position_id)
    data = payload.model_dump(exclude_unset=True)
    if "department_id" in data:
        await _validate_department(session, tenant_id, data["department_id"])
    for field, value in data.items():
        setattr(position, field, value)
    await session.flush()
    return position


async def list_positions(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    filters: PositionFilter,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[Position]:
    """Keyset-paginated positions ordered by code (D-014). The is_active / department filters narrow
    the set and fold into the cursor fingerprint so a cursor cannot bleed across views."""
    stmt = select(Position).where(Position.tenant_id == tenant_id)
    if filters.is_active is not None:
        stmt = stmt.where(Position.is_active == filters.is_active)
    if filters.department_id is not None:
        stmt = stmt.where(Position.department_id == filters.department_id)
    fingerprint = filter_fingerprint(filters.is_active, filters.department_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(Position.code, SortDirection.ASC)],
        pk=Position.id,
        cursor=cursor,
        limit=limit,
        filters=fingerprint,
    )
