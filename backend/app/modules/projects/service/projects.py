"""Project business logic (PLAN 11.1, D-056): CRUD + customer / cost-centre validation.

The service layer owns every rule (CLAUDE.md rule 7); the router stays thin. The optional
``customer_id`` is an OPAQUE sales customer id (D-029): validated to exist via
``sales/queries.customer_exists`` (the sanctioned cross-module read, STRUCTURE §5) — never a
cross-module FK. The optional ``cost_center_id`` is an OPAQUE finance cost-centre id validated via
``finance/queries.cost_center_exists``. ``from __future__ import annotations`` keeps
``Page[Project]`` (the ORM model) a string at import; the router re-validates page items.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.finance import queries as finance_queries
from app.modules.projects.models import Project
from app.modules.projects.schemas import ProjectCreate, ProjectFilter, ProjectUpdate
from app.modules.sales import queries as sales_queries


async def _validate_customer(
    session: AsyncSession, tenant_id: uuid.UUID, customer_id: uuid.UUID | None
) -> None:
    """A supplied customer id must exist in sales (D-029): validated via the sales queries contract,
    never a cross-module FK. None is skipped (the customer is optional)."""
    if customer_id is None:
        return
    if not await sales_queries.customer_exists(session, tenant_id, customer_id):
        raise ValidationFailedError(
            message="Referenced customer does not exist",
            code="projects.customer_not_found",
            details={"customer_id": str(customer_id)},
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
            code="projects.cost_center_not_found",
            details={"cost_center_id": str(cost_center_id)},
        )


async def get_project(
    session: AsyncSession, tenant_id: uuid.UUID, project_id: uuid.UUID
) -> Project:
    project = await session.get(Project, project_id)
    if project is None or project.tenant_id != tenant_id:
        raise NotFoundError(message="Project not found", code="projects.project_not_found")
    return project


async def create_project(
    session: AsyncSession, tenant_id: uuid.UUID, payload: ProjectCreate
) -> Project:
    """Create a project. Rejects a duplicate code (the DB UNIQUE is the backstop); validates the
    customer + cost centre exist when set."""
    existing = (
        await session.execute(
            select(Project.id).where(
                Project.tenant_id == tenant_id, Project.code == payload.code
            )
        )
    ).first()
    if existing is not None:
        raise ConflictError(
            message=f"Project with code {payload.code} already exists",
            code="projects.project_code_conflict",
            details={"code": payload.code},
        )
    await _validate_customer(session, tenant_id, payload.customer_id)
    await _validate_cost_center(session, tenant_id, payload.cost_center_id)
    project = Project(
        tenant_id=tenant_id,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        # ApiModel sets use_enum_values=True, so payload enum fields are already their string value.
        status=payload.status,
        customer_id=payload.customer_id,
        cost_center_id=payload.cost_center_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        budget_amount=payload.budget_amount,
        is_active=payload.is_active,
    )
    session.add(project)
    await session.flush()
    return project


async def update_project(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    payload: ProjectUpdate,
) -> Project:
    """Partial update (D-010: mutate the loaded object so the audit diff is captured). ``code`` is
    immutable and absent from the schema; a changed customer / cost centre is re-validated."""
    project = await get_project(session, tenant_id, project_id)
    data = payload.model_dump(exclude_unset=True)
    if "customer_id" in data:
        await _validate_customer(session, tenant_id, data["customer_id"])
    if "cost_center_id" in data:
        await _validate_cost_center(session, tenant_id, data["cost_center_id"])
    for field, value in data.items():
        setattr(project, field, value)
    await session.flush()
    return project


async def list_projects(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    filters: ProjectFilter,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[Project]:
    """Keyset-paginated projects ordered by code (D-014). The status filter narrows the set
    (index-served by (tenant, status)) and folds into the cursor fingerprint so a cursor cannot
    bleed across views."""
    stmt = select(Project).where(Project.tenant_id == tenant_id)
    if filters.status is not None:
        stmt = stmt.where(Project.status == filters.status)
    fingerprint = filter_fingerprint(filters.status)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(Project.code, SortDirection.ASC)],
        pk=Project.id,
        cursor=cursor,
        limit=limit,
        filters=fingerprint,
    )
