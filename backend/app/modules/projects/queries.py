"""Projects' cross-module read interface (STRUCTURE §5 / D-056).

Projects sits ABOVE finance, hr and sales in the dependency order; nothing imports this yet (it is
the newest module), but it is the ONLY projects file a later module may import — kept thin and
stable. The service and router use these reads too. Every function takes an explicit ``tenant_id``
and runs under the caller's tenant context, so the D-007 filter applies on top — ordinary
tenant-scoped reads.

``wbs_element_exists`` is exposed so a FUTURE projects-owned posting gate (or finance/hr validation,
once the dependency direction allows it) COULD validate a WBS dimension before a posting tags it —
TODAY finance/HR treat the WBS id as OPAQUE and never call this (D-029 keeps finance at the bottom).
``wbs_elements_for_project`` is the SET-BASED read the cost report drives: ONE query returns every
WBS element of a project (PERFORMANCE §6: no per-WBS N+1 loading the structure).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.models import Project, WbsElement


async def get_project(
    session: AsyncSession, tenant_id: uuid.UUID, project_id: uuid.UUID
) -> Project | None:
    """The project with ``project_id`` in the tenant, or None. A point lookup on the PK."""
    stmt = select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def project_exists(
    session: AsyncSession, tenant_id: uuid.UUID, project_id: uuid.UUID
) -> bool:
    """Whether a project with ``project_id`` exists in the tenant (a cheap id probe)."""
    stmt = select(Project.id).where(Project.tenant_id == tenant_id, Project.id == project_id)
    return (await session.execute(stmt)).first() is not None


async def get_wbs_element(
    session: AsyncSession, tenant_id: uuid.UUID, wbs_element_id: uuid.UUID
) -> WbsElement | None:
    """The WBS element with ``wbs_element_id`` in the tenant, or None. A point lookup on the PK."""
    stmt = select(WbsElement).where(
        WbsElement.tenant_id == tenant_id, WbsElement.id == wbs_element_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def wbs_element_exists(
    session: AsyncSession, tenant_id: uuid.UUID, wbs_element_id: uuid.UUID
) -> bool:
    """Whether a WBS element with ``wbs_element_id`` exists in the tenant (D-056). The
    costing-object id probe a future posting gate would call to validate a project dimension —
    finance/HR treat the id as OPAQUE today and never call this (D-029)."""
    stmt = select(WbsElement.id).where(
        WbsElement.tenant_id == tenant_id, WbsElement.id == wbs_element_id
    )
    return (await session.execute(stmt)).first() is not None


async def wbs_elements_for_project(
    session: AsyncSession, tenant_id: uuid.UUID, project_id: uuid.UUID
) -> list[WbsElement]:
    """Every WBS element of one project (D-056), ordered by code — the SET-BASED read the WBS tree
    view and the cost report both drive (PERFORMANCE §6: ONE query, no per-WBS N+1). Index-served by
    (tenant, project_id, status)."""
    stmt = (
        select(WbsElement)
        .where(WbsElement.tenant_id == tenant_id, WbsElement.project_id == project_id)
        .order_by(WbsElement.code)
    )
    return list((await session.execute(stmt)).scalars().all())
