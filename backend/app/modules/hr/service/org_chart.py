"""Org-chart assembly (PLAN 10.1, D-052): build the reporting tree from the bounded recursive read.

``org_chart`` turns ``hr/queries.org_chart_for`` (ONE query loads every employee; PERFORMANCE §6 —
no
per-node N+1) into nested ``OrgChartNode`` trees. The recursion is bounded by
``MAX_HIERARCHY_DEPTH``
AND by a ``visited`` set, so even a malformed cycle (should be impossible given the create/update
cycle guards) can never spin forever or duplicate a node. The chart carries name/code/title only —
no
compensation/PII — so it is safe for any ``hr.employee.read`` holder without a masking concern.

When ``root_employee_id`` is given the chart is the sub-tree anchored on that one manager; otherwise
it is every top-level employee (no manager) and their reports.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.hr import queries as hr_queries
from app.modules.hr.constants import MAX_HIERARCHY_DEPTH
from app.modules.hr.models import Employee
from app.modules.hr.schemas import OrgChartNode, OrgChartResponse


def _build_node(
    employee: Employee,
    children: dict[uuid.UUID, list[Employee]],
    visited: set[uuid.UUID],
    depth: int,
) -> OrgChartNode:
    """Recursively assemble one node and its reports. ``visited`` prevents a cycle re-entering a
    node; ``depth`` caps the recursion at ``MAX_HIERARCHY_DEPTH`` (a leaf returns no reports past
    the cap — a structural safety net; the cycle guards keep real data far shallower)."""
    visited.add(employee.id)
    reports: list[OrgChartNode] = []
    if depth < MAX_HIERARCHY_DEPTH:
        for child in children.get(employee.id, []):
            if child.id not in visited:
                reports.append(_build_node(child, children, visited, depth + 1))
    return OrgChartNode(
        id=employee.id,
        employee_code=employee.employee_code,
        first_name=employee.first_name,
        last_name=employee.last_name,
        position_id=employee.position_id,
        department_id=employee.department_id,
        reports=reports,
    )


async def org_chart(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    root_employee_id: uuid.UUID | None = None,
) -> OrgChartResponse:
    """The reporting org chart (D-052). With ``root_employee_id`` the sub-tree under that manager
    (404 if they don't exist); without it, every top-level employee (no manager) as a root. ONE
    query loads the tenant's employees; the tree is built in memory, bounded by
    ``MAX_HIERARCHY_DEPTH``."""
    # Surface a clean 404 for an unknown anchor (org_chart_for returns empty roots otherwise).
    if root_employee_id is not None and not await hr_queries.employee_exists(
        session, tenant_id, root_employee_id
    ):
        raise NotFoundError(message="Employee not found", code="hr.employee_not_found")
    roots, children = await hr_queries.org_chart_for(session, tenant_id, root_employee_id)
    visited: set[uuid.UUID] = set()
    nodes = [_build_node(root, children, visited, 0) for root in roots]
    return OrgChartResponse(roots=nodes)
