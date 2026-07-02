"""WBS-element business logic (PLAN 11.1, D-056): CRUD + the parent-hierarchy cycle guard.

A WBS element belongs to a project and forms a tree via ``parent_id``. The service owns every rule
(CLAUDE.md rule 7): the owning project must exist; the code is unique WITHIN the project (not per
tenant); a parent (when set) must belong to the SAME project, exist, and not create a cycle
(``_assert_no_parent_cycle`` walks the would-be ancestor chain, the department-hierarchy precedent,
D-052). The element's ``id`` is the OPAQUE costing object a posting tags (D-056).

``from __future__ import annotations`` keeps ``Page[WbsElement]`` (the ORM model) a string at
import; the router re-validates page items.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.projects import queries as projects_queries
from app.modules.projects.constants import MAX_WBS_DEPTH
from app.modules.projects.models import WbsElement
from app.modules.projects.schemas import WbsElementCreate, WbsElementFilter, WbsElementUpdate
from app.modules.projects.service.projects import get_project


async def get_wbs_element(
    session: AsyncSession, tenant_id: uuid.UUID, wbs_element_id: uuid.UUID
) -> WbsElement:
    element = await session.get(WbsElement, wbs_element_id)
    if element is None or element.tenant_id != tenant_id:
        raise NotFoundError(message="WBS element not found", code="projects.wbs_not_found")
    return element


async def _assert_no_parent_cycle(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    element_id: uuid.UUID | None,
    parent_id: uuid.UUID | None,
) -> None:
    """Reject a WBS parent that is invalid or would create a cycle (D-056). The parent must exist
    and belong to the SAME project; walking UP from it must never reach ``element_id`` (the element
    being edited) — that would close a loop. A self-parent is the degenerate case. Bounded by
    ``MAX_WBS_DEPTH``."""
    if parent_id is None:
        return
    if parent_id == element_id:
        raise ValidationFailedError(
            message="A WBS element cannot be its own parent",
            code="projects.wbs_cycle",
            details={"wbs_element_id": str(element_id), "parent_id": str(parent_id)},
        )
    current_id: uuid.UUID | None = parent_id
    seen: set[uuid.UUID] = set()
    for _ in range(MAX_WBS_DEPTH):
        if current_id is None:
            return
        if current_id == element_id:
            raise ValidationFailedError(
                message="WBS parent would create a cycle",
                code="projects.wbs_cycle",
                details={"wbs_element_id": str(element_id), "parent_id": str(parent_id)},
            )
        if current_id in seen:
            return
        seen.add(current_id)
        parent = await projects_queries.get_wbs_element(session, tenant_id, current_id)
        if parent is None:
            raise ValidationFailedError(
                message="Referenced parent WBS element does not exist",
                code="projects.wbs_not_found",
                details={"parent_id": str(parent_id)},
            )
        if parent.project_id != project_id:
            raise ValidationFailedError(
                message="A WBS parent must belong to the same project",
                code="projects.wbs_parent_other_project",
                details={"parent_id": str(parent_id), "project_id": str(project_id)},
            )
        current_id = parent.parent_id
    raise ValidationFailedError(
        message="WBS hierarchy is too deep",
        code="projects.wbs_too_deep",
        details={"max_depth": MAX_WBS_DEPTH},
    )


async def _assert_code_free(
    session: AsyncSession, tenant_id: uuid.UUID, project_id: uuid.UUID, code: str
) -> None:
    """The code must be free WITHIN the project (D-056: unique per (tenant, project), not per
    tenant). The DB UNIQUE is the backstop."""
    existing = (
        await session.execute(
            select(WbsElement.id).where(
                WbsElement.tenant_id == tenant_id,
                WbsElement.project_id == project_id,
                WbsElement.code == code,
            )
        )
    ).first()
    if existing is not None:
        raise ConflictError(
            message=f"WBS element with code {code} already exists in this project",
            code="projects.wbs_code_conflict",
            details={"code": code, "project_id": str(project_id)},
        )


async def create_wbs_element(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    payload: WbsElementCreate,
) -> WbsElement:
    """Create a WBS element under a project. The project must exist; the code is unique within it;
    a parent (when set) must belong to the same project and not create a cycle."""
    await get_project(session, tenant_id, project_id)  # 404 if missing / cross-tenant
    await _assert_code_free(session, tenant_id, project_id, payload.code)
    await _assert_no_parent_cycle(session, tenant_id, project_id, None, payload.parent_id)
    element = WbsElement(
        tenant_id=tenant_id,
        project_id=project_id,
        code=payload.code,
        name=payload.name,
        parent_id=payload.parent_id,
        # ApiModel sets use_enum_values=True, so payload enum fields are already their string value.
        status=payload.status,
        is_billable=payload.is_billable,
        budget_amount=payload.budget_amount,
    )
    session.add(element)
    await session.flush()
    return element


async def update_wbs_element(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    wbs_element_id: uuid.UUID,
    payload: WbsElementUpdate,
) -> WbsElement:
    """Partial update (D-010: mutate the loaded object so the audit diff is captured). ``code`` and
    ``project_id`` are immutable and absent; a changed parent is re-validated (same project, exists,
    no cycle)."""
    element = await get_wbs_element(session, tenant_id, wbs_element_id)
    data = payload.model_dump(exclude_unset=True)
    if "parent_id" in data:
        await _assert_no_parent_cycle(
            session, tenant_id, element.project_id, wbs_element_id, data["parent_id"]
        )
    for field, value in data.items():
        setattr(element, field, value)
    await session.flush()
    return element


async def list_wbs_elements(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    filters: WbsElementFilter,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[WbsElement]:
    """Keyset-paginated WBS elements of one project ordered by code (D-014) — the WBS tree the
    detail view renders. The status filter narrows the set (index-served by (tenant, project_id,
    status)) and folds into the cursor fingerprint. The project must exist (404 otherwise)."""
    await get_project(session, tenant_id, project_id)
    stmt = select(WbsElement).where(
        WbsElement.tenant_id == tenant_id, WbsElement.project_id == project_id
    )
    if filters.status is not None:
        stmt = stmt.where(WbsElement.status == filters.status)
    fingerprint = filter_fingerprint(project_id, filters.status)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(WbsElement.code, SortDirection.ASC)],
        pk=WbsElement.id,
        cursor=cursor,
        limit=limit,
        filters=fingerprint,
    )
