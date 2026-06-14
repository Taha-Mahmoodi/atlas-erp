"""Equipment business logic (PLAN 9.2, D-051): CRUD + cost-centre validation.

The service layer owns every rule (CLAUDE.md rule 7); the router stays thin. The optional
``cost_center_id`` is an OPAQUE finance cost-centre id (D-029): validated to exist via
``finance/queries.cost_center_exists`` (the sanctioned cross-module read, STRUCTURE §5) — never a
cross-module FK. ``from __future__ import annotations`` keeps ``Page[Equipment]`` (the ORM model) a
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
from app.modules.maintenance.models import Equipment
from app.modules.maintenance.schemas import (
    EquipmentCreate,
    EquipmentFilter,
    EquipmentUpdate,
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
            code="maintenance.cost_center_not_found",
            details={"cost_center_id": str(cost_center_id)},
        )


async def get_equipment(
    session: AsyncSession, tenant_id: uuid.UUID, equipment_id: uuid.UUID
) -> Equipment:
    equipment = await session.get(Equipment, equipment_id)
    if equipment is None or equipment.tenant_id != tenant_id:
        raise NotFoundError(
            message="Equipment not found", code="maintenance.equipment_not_found"
        )
    return equipment


async def create_equipment(
    session: AsyncSession, tenant_id: uuid.UUID, payload: EquipmentCreate
) -> Equipment:
    """Create a piece of equipment. Rejects a duplicate code (the DB UNIQUE is the backstop);
    validates the cost centre exists in finance when set."""
    existing = (
        await session.execute(
            select(Equipment.id).where(
                Equipment.tenant_id == tenant_id, Equipment.code == payload.code
            )
        )
    ).first()
    if existing is not None:
        raise ConflictError(
            message=f"Equipment with code {payload.code} already exists",
            code="maintenance.equipment_code_conflict",
            details={"code": payload.code},
        )
    await _validate_cost_center(session, tenant_id, payload.cost_center_id)
    equipment = Equipment(
        tenant_id=tenant_id,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        # ApiModel sets use_enum_values=True, so payload enum fields are already their string value.
        status=payload.status,
        location=payload.location,
        manufacturer=payload.manufacturer,
        model=payload.model,
        serial_number=payload.serial_number,
        commissioned_date=payload.commissioned_date,
        cost_center_id=payload.cost_center_id,
        notes=payload.notes,
    )
    session.add(equipment)
    await session.flush()
    return equipment


async def update_equipment(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    equipment_id: uuid.UUID,
    payload: EquipmentUpdate,
) -> Equipment:
    """Partial update (D-010: mutate the loaded object so the audit diff is captured). ``code`` is
    immutable and absent from the schema; a changed cost centre is re-validated. ApiModel sets
    use_enum_values=True, so a dumped enum field is already its string value (no .value needed)."""
    equipment = await get_equipment(session, tenant_id, equipment_id)
    data = payload.model_dump(exclude_unset=True)
    if "cost_center_id" in data:
        await _validate_cost_center(session, tenant_id, data["cost_center_id"])
    for field, value in data.items():
        setattr(equipment, field, value)
    await session.flush()
    return equipment


async def list_equipment(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    filters: EquipmentFilter,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[Equipment]:
    """Keyset-paginated equipment ordered by code (D-014). The status filter narrows the set
    (index-served by (tenant, status)) and folds into the cursor fingerprint so a cursor cannot
    bleed across views."""
    stmt = select(Equipment).where(Equipment.tenant_id == tenant_id)
    if filters.status is not None:
        # ApiModel sets use_enum_values=True, so filters.status is already its string value (a
        # StrEnum compares equal to its value either way).
        stmt = stmt.where(Equipment.status == filters.status)
    fingerprint = filter_fingerprint(filters.status)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(Equipment.code, SortDirection.ASC)],
        pk=Equipment.id,
        cursor=cursor,
        limit=limit,
        filters=fingerprint,
    )
