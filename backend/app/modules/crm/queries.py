"""CRM's cross-module read interface (STRUCTURE §5 / D-057).

CRM sits ABOVE finance, inventory, hr and sales in the dependency order. Nothing imports this file
in
v1 (CRM is the newest module), but it is the ONLY crm file another module could import — kept thin
and
stable. The service and router use these reads too. Every function takes an explicit ``tenant_id``
and
runs under the caller's tenant context, so the D-007 filter applies on top — ordinary tenant-scoped
reads.

SALES does NOT import this file. The convert flow is one-directional: CRM reads ``sales/queries``
(``customer_exists``) DOWNWARD, and SALES imports only ``crm/events`` (declarative, the §5
events-only
allowance) — so there is NO cycle (D-057).

``activities_for`` is the SET-BASED read the activities list drives (one query per parent); the
get_lead / get_opportunity point reads back the headers the service + router resolve.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crm.models import Activity, Lead, Opportunity, OpportunityLine


async def get_lead(
    session: AsyncSession, tenant_id: uuid.UUID, lead_id: uuid.UUID
) -> Lead | None:
    """The lead with ``lead_id`` in the tenant, or None. A point lookup on the PK."""
    stmt = select(Lead).where(Lead.tenant_id == tenant_id, Lead.id == lead_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def lead_exists(
    session: AsyncSession, tenant_id: uuid.UUID, lead_id: uuid.UUID
) -> bool:
    """Whether a lead with ``lead_id`` exists in the tenant (a cheap id probe — the activity-parent
    check)."""
    stmt = select(Lead.id).where(Lead.tenant_id == tenant_id, Lead.id == lead_id)
    return (await session.execute(stmt)).first() is not None


async def get_opportunity(
    session: AsyncSession, tenant_id: uuid.UUID, opportunity_id: uuid.UUID
) -> Opportunity | None:
    """The opportunity with ``opportunity_id`` in the tenant, or None. A point lookup on the PK."""
    stmt = select(Opportunity).where(
        Opportunity.tenant_id == tenant_id, Opportunity.id == opportunity_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def opportunity_exists(
    session: AsyncSession, tenant_id: uuid.UUID, opportunity_id: uuid.UUID
) -> bool:
    """Whether an opportunity with ``opportunity_id`` exists in the tenant (the activity-parent
    check)."""
    stmt = select(Opportunity.id).where(
        Opportunity.tenant_id == tenant_id, Opportunity.id == opportunity_id
    )
    return (await session.execute(stmt)).first() is not None


async def opportunity_lines(
    session: AsyncSession, tenant_id: uuid.UUID, opportunity_id: uuid.UUID
) -> list[OpportunityLine]:
    """Every line of one opportunity (D-057), ordered by line_number — the SET-BASED read the detail
    view + the convert flow drive (PERFORMANCE §6: ONE query, no per-line N+1). Index-served by
    (tenant, opportunity_id)."""
    stmt = (
        select(OpportunityLine)
        .where(
            OpportunityLine.tenant_id == tenant_id,
            OpportunityLine.opportunity_id == opportunity_id,
        )
        .order_by(OpportunityLine.line_number)
    )
    return list((await session.execute(stmt)).scalars().all())


async def opportunities_by_stage(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    owner_employee_id: uuid.UUID | None = None,
    per_stage_limit: int = 100,
) -> list[Opportunity]:
    """The opportunities for the KANBAN board (D-057), newest first — ONE bounded query the service
    groups by stage in memory (PERFORMANCE §6: no per-stage N+1). Optionally narrowed to one owner.
    Bounded by ``per_stage_limit`` stages × a generous global cap so the board never loads an
    unbounded set; the service slices each stage's cards to ``per_stage_limit``. Index-served by
    (tenant, stage) / (tenant, owner_employee_id)."""
    stmt = select(Opportunity).where(Opportunity.tenant_id == tenant_id)
    if owner_employee_id is not None:
        stmt = stmt.where(Opportunity.owner_employee_id == owner_employee_id)
    # Six stages × the per-column cap bounds the rows loaded for the board (a hard ceiling so a
    # tenant
    # with thousands of opportunities never streams them all into one response).
    global_cap = per_stage_limit * 6
    stmt = stmt.order_by(Opportunity.created_at.desc(), Opportunity.id.desc()).limit(global_cap)
    return list((await session.execute(stmt)).scalars().all())


async def activities_for(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    lead_id: uuid.UUID | None = None,
    opportunity_id: uuid.UUID | None = None,
) -> list[Activity]:
    """Every activity logged against one lead OR one opportunity (D-057), newest first — the read
    the
    detail timeline drives. Exactly one of ``lead_id`` / ``opportunity_id`` is given (the router
    enforces it). Index-served by (tenant, lead_id) / (tenant, opportunity_id)."""
    stmt = select(Activity).where(Activity.tenant_id == tenant_id)
    if lead_id is not None:
        stmt = stmt.where(Activity.lead_id == lead_id)
    if opportunity_id is not None:
        stmt = stmt.where(Activity.opportunity_id == opportunity_id)
    stmt = stmt.order_by(Activity.created_at.desc(), Activity.id.desc())
    return list((await session.execute(stmt)).scalars().all())
