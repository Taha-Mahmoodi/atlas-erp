"""Payroll HTTP layer (PLAN 10.4, D-055), included into the hr router.

A sibling sub-router under the same ``/api/v1/hr`` prefix, mounted by ``router.include_router`` in
router.py (the leave/timesheet-router precedent — ONE module surface at ``/api/v1/hr``, no second
mount in main.py). REST:

- payroll-runs: create (compute a DRAFT gross→net run), a filtered + paginated list
  (status / period range), GET /{id} (the run + its per-employee lines), post (post the consolidated
  finance journal via the event bus), cancel (a DRAFT run only).

RBAC (D-009; the manage vs post split, the leave/timesheet ``.approve`` precedent): runs + lines are
read by ``hr.payroll.read``; create / cancel by ``hr.payroll.manage``; post by the DISTINCT
``hr.payroll.post`` key (the value-bearing transition that hits the GL). A ``.manage`` holder can
compute a run but is 403 on post. Writes commit through ``run_in_uow`` (D-011) so audit rows AND the
event-driven finance journal ride the same transaction; create / post are IDEMPOTENT (D-013).
PERFORMANCE §6: the list is an O(1) paginated query; GET /{id} is two point reads.

THE NON-COMPLIANCE FLAG (D-055): the run computes a SIMPLISTIC flat-tax gross→net (no brackets, no
social security, no deductions). See docs/modules/hr.md.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import date

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.hr import service
from app.modules.hr.constants import (
    HR_PAYROLL_MANAGE,
    HR_PAYROLL_POST,
    HR_PAYROLL_READ,
    PayrollRunStatus,
)
from app.modules.hr.payroll_schemas import (
    PayrollRunCreate,
    PayrollRunDetail,
    PayrollRunFilter,
    PayrollRunLineRead,
    PayrollRunPost,
    PayrollRunRead,
)

payroll_router = APIRouter(tags=["hr-payroll"])
_CursorParamsDep = Depends(cursor_params)
_CreateIdem = Depends(Idempotent("hr.payroll.create"))
_PostIdem = Depends(Idempotent("hr.payroll.post"))


async def _commit_run(
    session: SessionDep, work: Callable[[], Awaitable[object]]
) -> PayrollRunRead:
    """Run a payroll service call inside the D-011 uow and return it refreshed + validated in the
    async context (the hr _commit_read twin)."""
    holder: dict[str, PayrollRunRead] = {}

    async def _work() -> None:
        run = await work()
        await session.refresh(run)
        holder["read"] = PayrollRunRead.model_validate(run)

    await run_in_uow(session, _work)
    return holder["read"]


@payroll_router.post(
    "/payroll-runs",
    response_model=PayrollRunRead,
    status_code=201,
    dependencies=[Depends(require_permission(HR_PAYROLL_MANAGE))],
)
async def create_payroll_run(
    payload: PayrollRunCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _CreateIdem,
) -> PayrollRunRead:
    """Compute a DRAFT gross→net payroll run (PLAN 10.4). IDEMPOTENT (D-013)."""
    holder: dict[str, PayrollRunRead] = {}

    async def work() -> None:
        run = await service.create_payroll_run(session, current.tenant_id, payload)
        await session.refresh(run)
        holder["read"] = await idem.capture(PayrollRunRead.model_validate(run))

    await run_in_uow(session, work)
    return holder["read"]


@payroll_router.get(
    "/payroll-runs",
    response_model=Page[PayrollRunRead],
    dependencies=[Depends(require_permission(HR_PAYROLL_READ))],
)
async def list_payroll_runs(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = _CursorParamsDep,
    status: PayrollRunStatus | None = None,
    period_from: date | None = None,
    period_to: date | None = None,
) -> Page[PayrollRunRead]:
    """Paginated payroll runs, newest period first (PLAN 10.4). Filters: status / period range (on
    period_start)."""
    filters = PayrollRunFilter(status=status, period_from=period_from, period_to=period_to)
    page = await service.list_payroll_runs(
        session, current.tenant_id, filters=filters, cursor=params.cursor, limit=params.limit
    )
    return map_page(page, PayrollRunRead)


@payroll_router.get(
    "/payroll-runs/{run_id}",
    response_model=PayrollRunDetail,
    dependencies=[Depends(require_permission(HR_PAYROLL_READ))],
)
async def get_payroll_run(
    run_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> PayrollRunDetail:
    """A payroll run plus its per-employee lines (PLAN 10.4). 404 if the run does not exist."""
    run = await service.get_payroll_run(session, current.tenant_id, run_id)
    lines = await service.list_payroll_lines(session, current.tenant_id, run_id)
    return PayrollRunDetail(
        **PayrollRunRead.model_validate(run).model_dump(),
        lines=[PayrollRunLineRead.model_validate(line) for line in lines],
    )


@payroll_router.post(
    "/payroll-runs/{run_id}/post",
    response_model=PayrollRunRead,
    dependencies=[Depends(require_permission(HR_PAYROLL_POST))],
)
async def post_payroll_run(
    run_id: uuid.UUID,
    payload: PayrollRunPost,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _PostIdem,
) -> PayrollRunRead:
    """Post a DRAFT payroll run's consolidated finance journal via the event bus (PLAN 10.4, the
    ``hr.payroll.post`` action). The journal (Dr salary-expense by cost centre / Cr
    payroll-tax-payable / Cr wages-payable) posts in the SAME transaction; a closed pay-date period
    rolls the whole post back. IDEMPOTENT (D-013)."""
    holder: dict[str, PayrollRunRead] = {}

    async def work() -> None:
        if payload.notes is not None:
            run = await service.get_payroll_run(session, current.tenant_id, run_id)
            run.notes = payload.notes
        run = await service.post_payroll_run(session, current.tenant_id, run_id)
        await session.refresh(run)
        holder["read"] = await idem.capture(PayrollRunRead.model_validate(run))

    await run_in_uow(session, work)
    return holder["read"]


@payroll_router.post(
    "/payroll-runs/{run_id}/cancel",
    response_model=PayrollRunRead,
    dependencies=[Depends(require_permission(HR_PAYROLL_MANAGE))],
)
async def cancel_payroll_run(
    run_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> PayrollRunRead:
    """Cancel a DRAFT payroll run (PLAN 10.4): DRAFT → CANCELLED. A posted run is corrected by
    reversing its journal in finance, never cancelled."""
    return await _commit_run(
        session, lambda: service.cancel_payroll_run(session, current.tenant_id, run_id)
    )


@payroll_router.get(
    "/payroll-runs/{run_id}/lines",
    response_model=list[PayrollRunLineRead],
    dependencies=[Depends(require_permission(HR_PAYROLL_READ))],
)
async def list_payroll_lines(
    run_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> list[PayrollRunLineRead]:
    """The per-employee lines of one payroll run (PLAN 10.4). 404 if the run does not exist."""
    lines = await service.list_payroll_lines(session, current.tenant_id, run_id)
    return [PayrollRunLineRead.model_validate(line) for line in lines]
