"""Customer-group business logic (PLAN 7.1): the lean grouping master CRUD.

The service layer owns every rule (CLAUDE.md rule 7); the router stays thin. Rules here: ``code``
uniqueness per tenant (friendly ConflictError before the DB UNIQUE would raise); ``code`` is
immutable after creation (customers + price lists reference the group). A group carries no pricing —
it is a grouping key only.

``from __future__ import annotations`` keeps ``Page[CustomerGroup]`` (the ORM model) a string at
import; the router re-validates page items.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.pagination import (
    DEFAULT_LIMIT,
    OrderKey,
    SortDirection,
    paginate,
)
from app.core.schemas import Page
from app.modules.sales.models import CustomerGroup
from app.modules.sales.schemas import CustomerGroupCreate, CustomerGroupUpdate


async def _group_by_code(
    session: AsyncSession, tenant_id: uuid.UUID, code: str
) -> CustomerGroup | None:
    stmt = select(CustomerGroup).where(
        CustomerGroup.tenant_id == tenant_id, CustomerGroup.code == code
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_customer_group(
    session: AsyncSession, tenant_id: uuid.UUID, group_id: uuid.UUID
) -> CustomerGroup:
    group = await session.get(CustomerGroup, group_id)
    if group is None or group.tenant_id != tenant_id:
        raise NotFoundError(
            message="Customer group not found", code="sales.customer_group_not_found"
        )
    return group


async def create_customer_group(
    session: AsyncSession, tenant_id: uuid.UUID, payload: CustomerGroupCreate
) -> CustomerGroup:
    """Create a customer group. Rejects a duplicate code (friendly ConflictError before the DB
    UNIQUE backstop)."""
    if await _group_by_code(session, tenant_id, payload.code) is not None:
        raise ConflictError(
            message=f"A customer group with code {payload.code} already exists",
            code="sales.customer_group_code_conflict",
            details={"code": payload.code},
        )
    group = CustomerGroup(tenant_id=tenant_id, code=payload.code, name=payload.name)
    session.add(group)
    await session.flush()
    return group


async def update_customer_group(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    group_id: uuid.UUID,
    payload: CustomerGroupUpdate,
) -> CustomerGroup:
    """Partial update (D-010: mutate the loaded object so the audit diff is captured). ``code`` is
    immutable and absent from the schema; only ``name`` is editable."""
    group = await get_customer_group(session, tenant_id, group_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(group, field, value)
    await session.flush()
    return group


async def list_customer_groups(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[CustomerGroup]:
    """Keyset-paginated customer-group list ordered by code (D-014)."""
    stmt = select(CustomerGroup).where(CustomerGroup.tenant_id == tenant_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(CustomerGroup.code, SortDirection.ASC)],
        pk=CustomerGroup.id,
        cursor=cursor,
        limit=limit,
    )
