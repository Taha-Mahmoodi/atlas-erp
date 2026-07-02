"""MRP HTTP layer (PLAN 8.3), included into the manufacturing router.

A sibling sub-router under the same ``/api/v1/manufacturing`` prefix, mounted by
``router.include_router`` in router.py (the production_order_router precedent — ONE module surface,
no second mount in main.py).

RBAC (D-009; distinct authorities):
  - read runs / planned orders / capacity by ``manufacturing.mrp.read`` (the run + capacity reads)
    and ``manufacturing.planned_order.read`` (the planned-order reads);
  - RUN MRP by ``manufacturing.mrp.run``;
  - firm / convert / cancel a planned order by ``manufacturing.planned_order.manage``.

The RUN is ALWAYS a BACKGROUND JOB (PERFORMANCE §3, D-049): the endpoint submits a
``manufacturing.mrp_run`` job and returns 202 ``JobSubmitted`` for /api/v1/jobs polling — the
depreciation-run background path, minus the inline branch (MRP scans every item, so it is always a
job). The submit is IDEMPOTENT (D-013): a replayed Idempotency-Key returns the SAME job id. Convert
is idempotent too (a real document is created). Lists are paginated (PERFORMANCE §6).
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep, SessionFactoryDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.jobs import schedule_job, submit_job
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import JobSubmitted, Page
from app.modules.manufacturing import service
from app.modules.manufacturing.constants import (
    MFG_MRP_READ,
    MFG_MRP_RUN,
    MFG_PLANNED_ORDER_MANAGE,
    MFG_PLANNED_ORDER_READ,
    MRP_DEFAULT_HORIZON_DAYS,
    MRP_RUN_JOB,
    MrpRunStatus,
    PlannedOrderStatus,
    PlannedOrderType,
)
from app.modules.manufacturing.schemas import (
    CapacityLoadRead,
    MrpRunRead,
    MrpRunRequest,
    MrpRunSummary,
    PlannedOrderConvertRequest,
    PlannedOrderRead,
)

mrp_router = APIRouter(tags=["manufacturing-mrp"])

_CursorParamsDep = Depends(cursor_params)
_RunIdem = Depends(Idempotent("manufacturing.mrp.run"))
_ConvertIdem = Depends(Idempotent("manufacturing.planned_order.convert"))
_MrpReadGuard = Depends(require_permission(MFG_MRP_READ))
_PlannedReadGuard = Depends(require_permission(MFG_PLANNED_ORDER_READ))
_PlannedManageGuard = Depends(require_permission(MFG_PLANNED_ORDER_MANAGE))


@mrp_router.post(
    "/mrp/runs",
    response_model=JobSubmitted,
    status_code=202,
    dependencies=[Depends(require_permission(MFG_MRP_RUN))],
)
async def run_mrp(
    payload: MrpRunRequest,
    current: CurrentUserDep,
    session: SessionDep,
    factory: SessionFactoryDep,
    idem: IdempotentDep = _RunIdem,
) -> JobSubmitted:
    """Run MRP (D-049): ALWAYS submits a background job (the run scans every item) and returns
    202 {job_id} for /api/v1/jobs polling. IDEMPOTENT (D-013): a replayed key returns the SAME
    job id (the PENDING row commits with the capture)."""
    holder: dict[str, JobSubmitted] = {}
    job_id_holder: dict[str, uuid.UUID] = {}
    run_date = payload.run_date or date.today()
    horizon = payload.horizon_days or MRP_DEFAULT_HORIZON_DAYS

    async def work() -> None:
        job_payload: dict[str, str | int] = {
            "run_date": run_date.isoformat(),
            "horizon_days": horizon,
        }
        if payload.warehouse_id is not None:
            job_payload["warehouse_id"] = str(payload.warehouse_id)
        job = await submit_job(
            session,
            current.tenant_id,
            MRP_RUN_JOB,
            job_payload,
            submitted_by=current.user_id,
        )
        job_id_holder["job_id"] = job.id
        holder["read"] = await idem.capture(
            JobSubmitted(job_id=job.id, status=job.status), status_code=202
        )

    await run_in_uow(session, work)
    schedule_job(job_id_holder["job_id"], factory)
    return holder["read"]


@mrp_router.get("/mrp/runs", response_model=Page[MrpRunRead], dependencies=[_MrpReadGuard])
async def list_mrp_runs(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = _CursorParamsDep,
    status: MrpRunStatus | None = None,
) -> Page[MrpRunRead]:
    page = await service.list_mrp_runs(
        session, current.tenant_id, status=status, cursor=params.cursor, limit=params.limit
    )
    return map_page(page, MrpRunRead)


@mrp_router.get("/mrp/runs/{run_id}", response_model=MrpRunSummary, dependencies=[_MrpReadGuard])
async def get_mrp_run(
    run_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> MrpRunSummary:
    """The run header + its capacity loads (the planned orders are paginated separately)."""
    run = await service.get_mrp_run(session, current.tenant_id, run_id)
    loads = await service.capacity_for_run(session, current.tenant_id, run_id)
    header = MrpRunRead.model_validate(run)
    return MrpRunSummary(
        **header.model_dump(),
        capacity_loads=[CapacityLoadRead.model_validate(load) for load in loads],
    )


@mrp_router.get(
    "/mrp/runs/{run_id}/planned-orders",
    response_model=Page[PlannedOrderRead],
    dependencies=[_PlannedReadGuard],
)
async def list_planned_orders(
    run_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = _CursorParamsDep,
    order_type: PlannedOrderType | None = None,
    status: PlannedOrderStatus | None = None,
) -> Page[PlannedOrderRead]:
    # 404 on an unknown/foreign run (vs a silent empty page); 1 extra query, budget ≤3.
    await service.get_mrp_run(session, current.tenant_id, run_id)
    page = await service.planned_orders_for_run(
        session,
        current.tenant_id,
        run_id,
        order_type=order_type,
        status=status,
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, PlannedOrderRead)


@mrp_router.get(
    "/mrp/runs/{run_id}/capacity",
    response_model=list[CapacityLoadRead],
    dependencies=[_MrpReadGuard],
)
async def get_run_capacity(
    run_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> list[CapacityLoadRead]:
    """The run's rough-capacity loads, overloaded flagged + sorted first (PLAN 8.3)."""
    await service.get_mrp_run(session, current.tenant_id, run_id)
    loads = await service.capacity_for_run(session, current.tenant_id, run_id)
    return [CapacityLoadRead.model_validate(load) for load in loads]


@mrp_router.post(
    "/planned-orders/{planned_order_id}/firm",
    response_model=PlannedOrderRead,
    dependencies=[_PlannedManageGuard],
)
async def firm_planned_order(
    planned_order_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> PlannedOrderRead:
    """FIRM a planned order (PLAN 8.3): a re-run keeps it + nets it as supply."""
    holder: dict[str, PlannedOrderRead] = {}

    async def work() -> None:
        order = await service.firm_planned_order(session, current.tenant_id, planned_order_id)
        await session.refresh(order)
        holder["read"] = PlannedOrderRead.model_validate(order)

    await run_in_uow(session, work)
    return holder["read"]


@mrp_router.post(
    "/planned-orders/{planned_order_id}/convert",
    response_model=PlannedOrderRead,
    dependencies=[_PlannedManageGuard],
)
async def convert_planned_order(
    planned_order_id: uuid.UUID,
    payload: PlannedOrderConvertRequest,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _ConvertIdem,
) -> PlannedOrderRead:
    """CONVERT a planned order to a real document (PLAN 8.3, D-049): a MAKE order → a production
    order (intra-module); a BUY order → a procurement requisition (via the event bus). IDEMPOTENT
    (D-013): a retried request replays, never double-creates."""
    holder: dict[str, PlannedOrderRead] = {}

    async def work() -> None:
        order = await service.convert_planned_order(
            session, current.tenant_id, planned_order_id, warehouse_id=payload.warehouse_id
        )
        await session.refresh(order)
        holder["read"] = await idem.capture(PlannedOrderRead.model_validate(order))

    await run_in_uow(session, work)
    return holder["read"]


@mrp_router.post(
    "/planned-orders/{planned_order_id}/cancel",
    response_model=PlannedOrderRead,
    dependencies=[_PlannedManageGuard],
)
async def cancel_planned_order(
    planned_order_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> PlannedOrderRead:
    """CANCEL a planned order (PLAN 8.3): the row survives but adds no supply."""
    holder: dict[str, PlannedOrderRead] = {}

    async def work() -> None:
        order = await service.cancel_planned_order(session, current.tenant_id, planned_order_id)
        await session.refresh(order)
        holder["read"] = PlannedOrderRead.model_validate(order)

    await run_in_uow(session, work)
    return holder["read"]
