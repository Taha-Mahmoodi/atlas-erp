"""Cost-centre + profit-centre master-data CRUD (PLAN 4.7).

The service layer owns every rule (CLAUDE.md rule 7); the router stays thin. Cost/profit centres are
journal-line dimensions (D-021), so creating them is ordinary tenant-scoped master data with one
extra invariant: the ``parent_id`` hierarchy must stay ACYCLIC (a centre can never be its own
ancestor — the same walk-the-parent-chain guard the account-group tree uses).

Allocation-rule CRUD lives in ``service/allocation_rules.py`` and the run engine in
``service/allocation.py`` (split so each file stays under the STRUCTURE §3 400-line cap); this file
is centre master data only.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import OrderKey, SortDirection, paginate
from app.core.schemas import Page
from app.modules.finance.controlling_schemas import (
    CostCenterCreate,
    CostCenterUpdate,
    ProfitCenterCreate,
    ProfitCenterUpdate,
)
from app.modules.finance.models import CostCenter, ProfitCenter

# --- Cost centres -------------------------------------------------------------


async def get_cost_center(
    session: AsyncSession, tenant_id: uuid.UUID, cost_center_id: uuid.UUID
) -> CostCenter:
    center = await session.get(CostCenter, cost_center_id)
    if center is None or center.tenant_id != tenant_id:
        raise NotFoundError(message="Cost centre not found", code="finance.cost_center_not_found")
    return center


async def _cost_center_by_code(
    session: AsyncSession, tenant_id: uuid.UUID, code: str
) -> CostCenter | None:
    stmt = select(CostCenter).where(CostCenter.tenant_id == tenant_id, CostCenter.code == code)
    return (await session.execute(stmt)).scalar_one_or_none()


async def _assert_cost_center_no_cycle(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    center_id: uuid.UUID,
    new_parent_id: uuid.UUID,
) -> None:
    """Raise if making ``center_id`` a child of ``new_parent_id`` would form a cycle: walk from the
    prospective parent up its parent chain; reaching ``center_id`` means it is already an ancestor.
    A visited set bounds any pre-existing malformed tree."""
    current: uuid.UUID | None = new_parent_id
    visited: set[uuid.UUID] = set()
    while current is not None:
        if current == center_id:
            raise ValidationFailedError(
                message="The cost-centre hierarchy would form a cycle",
                code="finance.cost_center_cycle",
            )
        if current in visited:
            break
        visited.add(current)
        parent = await get_cost_center(session, tenant_id, current)
        current = parent.parent_id


async def create_cost_center(
    session: AsyncSession, tenant_id: uuid.UUID, payload: CostCenterCreate
) -> CostCenter:
    """Create a cost centre (PLAN 4.7). Rejects a duplicate code (the DB UNIQUE backstops it);
    validates the parent + default profit centre exist in the tenant. A new centre has no children,
    so a parent_id can never form a cycle at creation."""
    if await _cost_center_by_code(session, tenant_id, payload.code) is not None:
        raise ConflictError(
            message=f"A cost centre with code {payload.code} already exists",
            code="finance.cost_center_code_conflict",
            details={"code": payload.code},
        )
    if payload.parent_id is not None:
        await get_cost_center(session, tenant_id, payload.parent_id)
    if payload.default_profit_center_id is not None:
        await get_profit_center(session, tenant_id, payload.default_profit_center_id)
    center = CostCenter(
        tenant_id=tenant_id,
        code=payload.code,
        name=payload.name,
        parent_id=payload.parent_id,
        is_active=payload.is_active,
        manager_name=payload.manager_name,
        default_profit_center_id=payload.default_profit_center_id,
    )
    session.add(center)
    await session.flush()
    return center


async def update_cost_center(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    cost_center_id: uuid.UUID,
    payload: CostCenterUpdate,
) -> CostCenter:
    """Partial update of a cost centre (D-010: mutate the loaded object so the audit diff is
    captured). Reparenting is cycle-checked; a centre can never be its own parent."""
    center = await get_cost_center(session, tenant_id, cost_center_id)
    data = payload.model_dump(exclude_unset=True)
    if "parent_id" in data and data["parent_id"] is not None:
        new_parent = data["parent_id"]
        if new_parent == cost_center_id:
            raise ValidationFailedError(
                message="A cost centre cannot be its own parent",
                code="finance.cost_center_cycle",
            )
        await get_cost_center(session, tenant_id, new_parent)
        await _assert_cost_center_no_cycle(session, tenant_id, cost_center_id, new_parent)
    if data.get("default_profit_center_id") is not None:
        await get_profit_center(session, tenant_id, data["default_profit_center_id"])
    for field, value in data.items():
        setattr(center, field, value)
    await session.flush()
    return center


async def list_cost_centers(
    session: AsyncSession, tenant_id: uuid.UUID, *, cursor: str | None, limit: int
) -> Page[CostCenter]:
    """Keyset-paginated cost-centre list ordered by code (D-014)."""
    stmt = select(CostCenter).where(CostCenter.tenant_id == tenant_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(CostCenter.code, SortDirection.ASC)],
        pk=CostCenter.id,
        cursor=cursor,
        limit=limit,
    )


# --- Profit centres -----------------------------------------------------------


async def get_profit_center(
    session: AsyncSession, tenant_id: uuid.UUID, profit_center_id: uuid.UUID
) -> ProfitCenter:
    center = await session.get(ProfitCenter, profit_center_id)
    if center is None or center.tenant_id != tenant_id:
        raise NotFoundError(
            message="Profit centre not found", code="finance.profit_center_not_found"
        )
    return center


async def _profit_center_by_code(
    session: AsyncSession, tenant_id: uuid.UUID, code: str
) -> ProfitCenter | None:
    stmt = select(ProfitCenter).where(
        ProfitCenter.tenant_id == tenant_id, ProfitCenter.code == code
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _assert_profit_center_no_cycle(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    center_id: uuid.UUID,
    new_parent_id: uuid.UUID,
) -> None:
    current: uuid.UUID | None = new_parent_id
    visited: set[uuid.UUID] = set()
    while current is not None:
        if current == center_id:
            raise ValidationFailedError(
                message="The profit-centre hierarchy would form a cycle",
                code="finance.profit_center_cycle",
            )
        if current in visited:
            break
        visited.add(current)
        parent = await get_profit_center(session, tenant_id, current)
        current = parent.parent_id


async def create_profit_center(
    session: AsyncSession, tenant_id: uuid.UUID, payload: ProfitCenterCreate
) -> ProfitCenter:
    """Create a profit centre (PLAN 4.7). Rejects a duplicate code; validates the parent exists."""
    if await _profit_center_by_code(session, tenant_id, payload.code) is not None:
        raise ConflictError(
            message=f"A profit centre with code {payload.code} already exists",
            code="finance.profit_center_code_conflict",
            details={"code": payload.code},
        )
    if payload.parent_id is not None:
        await get_profit_center(session, tenant_id, payload.parent_id)
    center = ProfitCenter(
        tenant_id=tenant_id,
        code=payload.code,
        name=payload.name,
        parent_id=payload.parent_id,
        is_active=payload.is_active,
    )
    session.add(center)
    await session.flush()
    return center


async def update_profit_center(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    profit_center_id: uuid.UUID,
    payload: ProfitCenterUpdate,
) -> ProfitCenter:
    center = await get_profit_center(session, tenant_id, profit_center_id)
    data = payload.model_dump(exclude_unset=True)
    if "parent_id" in data and data["parent_id"] is not None:
        new_parent = data["parent_id"]
        if new_parent == profit_center_id:
            raise ValidationFailedError(
                message="A profit centre cannot be its own parent",
                code="finance.profit_center_cycle",
            )
        await get_profit_center(session, tenant_id, new_parent)
        await _assert_profit_center_no_cycle(session, tenant_id, profit_center_id, new_parent)
    for field, value in data.items():
        setattr(center, field, value)
    await session.flush()
    return center


async def list_profit_centers(
    session: AsyncSession, tenant_id: uuid.UUID, *, cursor: str | None, limit: int
) -> Page[ProfitCenter]:
    """Keyset-paginated profit-centre list ordered by code (D-014)."""
    stmt = select(ProfitCenter).where(ProfitCenter.tenant_id == tenant_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(ProfitCenter.code, SortDirection.ASC)],
        pk=ProfitCenter.id,
        cursor=cursor,
        limit=limit,
    )
