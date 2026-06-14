"""Employee HTTP layer (PLAN 10.1), included into the hr router.

A sibling sub-router under the same ``/api/v1/hr`` prefix, mounted by ``router.include_router`` in
router.py (the maintenance order_router precedent — ONE module surface, no second mount in main.py).
REST: employee CRUD with the D-009 MASKED Read, a filtered paginated list, the dedicated
compensation-write endpoint, and the org-chart endpoint.

RBAC (D-009; distinct authorities):
- read by ``hr.employee.read`` — but the masked compensation/PII serializes to ``None`` unless the
  principal ALSO holds ``hr.employee.read_compensation`` (the Masked serializer reads
  ``current_permissions``); so a plain reader sees the employee with pay/PII redacted.
- edit non-compensation fields by ``hr.employee.manage``.
- CREATE by ``hr.employee.manage`` AND ``hr.employee.read_compensation`` (create accepts initial
  compensation, so it requires the sensitive key too — a manage-only user cannot seed pay).
- the COMPENSATION endpoint by ``hr.employee.read_compensation`` (the sole post-create path that
  writes pay/PII — D-052).
- the org chart by ``hr.employee.read`` (structural, name/code only — no pay).

Writes commit through ``run_in_uow`` (D-011) so the employee row + audit rows ride one transaction.
The list is O(1) queries + paginated; masking adds no query (PERFORMANCE §6).
"""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.hr import service
from app.modules.hr.constants import (
    HR_EMPLOYEE_MANAGE,
    HR_EMPLOYEE_READ,
    HR_EMPLOYEE_READ_COMPENSATION,
    EmploymentStatus,
)
from app.modules.hr.schemas import (
    EmployeeCompensationUpdate,
    EmployeeCreate,
    EmployeeFilter,
    EmployeeRead,
    EmployeeUpdate,
    OrgChartResponse,
)

employee_router = APIRouter(tags=["hr-employees"])
_CursorParamsDep = Depends(cursor_params)


async def _commit_read[T](
    session: SessionDep, work: Callable[[], Awaitable[object]]
) -> EmployeeRead:
    """Run a service call inside the D-011 uow and return the employee refreshed + validated in the
    async context so a sync ``model_validate`` never trips MissingGreenlet (the maintenance _commit
    twin). The masking applies at serialization, reading the request's current_permissions."""
    holder: dict[str, EmployeeRead] = {}

    async def _work() -> None:
        employee = await work()
        await session.refresh(employee)
        holder["read"] = EmployeeRead.model_validate(employee)

    await run_in_uow(session, _work)
    return holder["read"]


# NOTE: /employees/org-chart is declared BEFORE /employees/{employee_id} so the literal path is
# matched ahead of the {employee_id} catch-all (FastAPI matches routes in declaration order).
@employee_router.get(
    "/employees/org-chart",
    response_model=OrgChartResponse,
    dependencies=[Depends(require_permission(HR_EMPLOYEE_READ))],
)
async def get_org_chart(
    current: CurrentUserDep,
    session: SessionDep,
    root_employee_id: uuid.UUID | None = None,
) -> OrgChartResponse:
    """The reporting org chart (PLAN 10.1, D-052): the whole tenant (top-level employees as roots)
    or the sub-tree under ``root_employee_id``. Structural only (name/code/title) — no compensation,
    so plain ``hr.employee.read`` suffices. ONE query loads the employees; the tree is built
    bounded-depth (PERFORMANCE §6)."""
    return await service.org_chart(session, current.tenant_id, root_employee_id)


@employee_router.post(
    "/employees",
    response_model=EmployeeRead,
    status_code=201,
    # Stacked guards (D-009): create accepts initial compensation, so BOTH the manage key AND the
    # sensitive read_compensation key are required — two require_permission deps, each a 403 on its
    # own missing key (the idiom for an AND of permissions; no extra core helper needed).
    dependencies=[
        Depends(require_permission(HR_EMPLOYEE_MANAGE)),
        Depends(require_permission(HR_EMPLOYEE_READ_COMPENSATION)),
    ],
)
async def create_employee(
    payload: EmployeeCreate, current: CurrentUserDep, session: SessionDep
) -> EmployeeRead:
    """Create an employee (PLAN 10.1). Requires BOTH ``hr.employee.manage`` and
    ``hr.employee.read_compensation`` because the create payload carries initial compensation/PII —
    a manage-only user cannot seed pay (D-052)."""
    return await _commit_read(
        session, lambda: service.create_employee(session, current.tenant_id, payload)
    )


@employee_router.get(
    "/employees",
    response_model=Page[EmployeeRead],
    dependencies=[Depends(require_permission(HR_EMPLOYEE_READ))],
)
async def list_employees(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = _CursorParamsDep,
    department_id: uuid.UUID | None = None,
    status: EmploymentStatus | None = None,
    manager_id: uuid.UUID | None = None,
) -> Page[EmployeeRead]:
    """Paginated employee list (PLAN 10.1). The compensation/PII in each item is masked unless the
    principal holds ``hr.employee.read_compensation`` (the Masked serializer, per request). Filters:
    department / status / manager."""
    filters = EmployeeFilter(department_id=department_id, status=status, manager_id=manager_id)
    page = await service.list_employees(
        session,
        current.tenant_id,
        filters=filters,
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, EmployeeRead)


@employee_router.get(
    "/employees/{employee_id}",
    response_model=EmployeeRead,
    dependencies=[Depends(require_permission(HR_EMPLOYEE_READ))],
)
async def get_employee(
    employee_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> EmployeeRead:
    """One employee (PLAN 10.1). Compensation/PII masked unless the principal holds
    ``hr.employee.read_compensation``."""
    employee = await service.get_employee(session, current.tenant_id, employee_id)
    return EmployeeRead.model_validate(employee)


@employee_router.patch(
    "/employees/{employee_id}",
    response_model=EmployeeRead,
    dependencies=[Depends(require_permission(HR_EMPLOYEE_MANAGE))],
)
async def update_employee(
    employee_id: uuid.UUID,
    payload: EmployeeUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> EmployeeRead:
    """Update an employee's NON-compensation fields (PLAN 10.1). The masked compensation/PII fields
    are not accepted here — they are written only via the compensation endpoint (D-009 write-side
    convention). The returned Read still masks pay unless the principal holds read_compensation."""
    return await _commit_read(
        session,
        lambda: service.update_employee(session, current.tenant_id, employee_id, payload),
    )


@employee_router.patch(
    "/employees/{employee_id}/compensation",
    response_model=EmployeeRead,
    dependencies=[Depends(require_permission(HR_EMPLOYEE_READ_COMPENSATION))],
)
async def set_employee_compensation(
    employee_id: uuid.UUID,
    payload: EmployeeCompensationUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> EmployeeRead:
    """The dedicated compensation/PII write path (PLAN 10.1, D-009/D-052), guarded by
    ``hr.employee.read_compensation`` — the SOLE post-create path that writes pay/PII. Only the set
    fields change; the returned Read shows the new values (the caller holds read_compensation)."""
    return await _commit_read(
        session,
        lambda: service.set_compensation(session, current.tenant_id, employee_id, payload),
    )
