"""Asset accounting HTTP layer (PLAN 4.10), included into the finance router.

A sibling sub-router exactly like bank_router/ap_router (one surface at ``/api/v1/finance``).
Reads are guarded by ``finance.asset.read``, asset writes by ``finance.asset.manage``, and
the depreciation run by ``finance.depreciation.run`` (D-009). Writes commit through
``run_in_uow`` (D-011). Activation and the depreciation run are IDEMPOTENT (D-013) — both
create financial documents.

**The run sync/background split** (PERFORMANCE §3): THIS router counts the period's eligible
assets — up to ``DEPRECIATION_RUN_SYNC_MAX_ASSETS`` (100) the run executes inline and returns
201 with the run; above that it submits a ``finance.depreciation_run`` job and returns
202 {job_id} for /api/v1/jobs polling. Both paths share one idempotent endpoint: the capture
commits atomically with the run (or the PENDING job row, so a replayed key returns the SAME
job id).
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Response

from app.core.deps import CurrentUserDep, SessionDep, SessionFactoryDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.jobs import schedule_job, submit_job
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import JobSubmitted, Page
from app.modules.finance import service
from app.modules.finance.assets_schemas import (
    AssetActivateRequest,
    AssetCreate,
    AssetRead,
    AssetRegisterReport,
    AssetRegisterRow,
    AssetUpdate,
    DepreciationEntryRead,
    DepreciationRunRead,
    DepreciationRunRequest,
)
from app.modules.finance.constants import (
    DEPRECIATION_RUN_JOB,
    DEPRECIATION_RUN_SYNC_MAX_ASSETS,
    FINANCE_ASSET_MANAGE,
    FINANCE_ASSET_READ,
    FINANCE_DEPRECIATION_RUN,
)

assets_router = APIRouter(tags=["finance-assets"])

CursorParamsDep = Depends(cursor_params)
_ActivateIdempotentDep = Depends(Idempotent("finance.asset.activate"))
_RunIdempotentDep = Depends(Idempotent("finance.depreciation.run"))
_ReadGuard = Depends(require_permission(FINANCE_ASSET_READ))
_ManageGuard = Depends(require_permission(FINANCE_ASSET_MANAGE))


@assets_router.post(
    "/assets", response_model=AssetRead, status_code=201, dependencies=[_ManageGuard]
)
async def create_asset(
    payload: AssetCreate, current: CurrentUserDep, session: SessionDep
) -> AssetRead:
    """Create a DRAFT asset (no number until activation, D-012)."""
    holder: dict[str, AssetRead] = {}

    async def work() -> None:
        asset = await service.create_asset(session, current.tenant_id, payload)
        await session.refresh(asset)
        holder["read"] = AssetRead.model_validate(asset)

    await run_in_uow(session, work)
    return holder["read"]


@assets_router.patch("/assets/{asset_id}", response_model=AssetRead, dependencies=[_ManageGuard])
async def update_asset(
    asset_id: uuid.UUID, payload: AssetUpdate, current: CurrentUserDep, session: SessionDep
) -> AssetRead:
    """Patch a DRAFT asset (409 once activated)."""
    holder: dict[str, AssetRead] = {}

    async def work() -> None:
        asset = await service.update_asset(session, current.tenant_id, asset_id, payload)
        await session.refresh(asset)
        holder["read"] = AssetRead.model_validate(asset)

    await run_in_uow(session, work)
    return holder["read"]


@assets_router.post(
    "/assets/{asset_id}/activate", response_model=AssetRead, dependencies=[_ManageGuard]
)
async def activate_asset(
    asset_id: uuid.UUID,
    payload: AssetActivateRequest,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _ActivateIdempotentDep,
) -> AssetRead:
    """Activate a DRAFT asset: claim the AST number; ``capitalize=true`` also posts the
    acquisition journal. IDEMPOTENT (D-013): a retried request replays, never re-posts."""
    holder: dict[str, AssetRead] = {}

    async def work() -> None:
        asset = await service.activate_asset(
            session, current.tenant_id, asset_id, capitalize=payload.capitalize
        )
        await session.refresh(asset)
        holder["read"] = await idem.capture(AssetRead.model_validate(asset))

    await run_in_uow(session, work)
    return holder["read"]


@assets_router.get("/assets", response_model=Page[AssetRead], dependencies=[_ReadGuard])
async def list_assets(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    status: str | None = None,
) -> Page[AssetRead]:
    page = await service.list_assets(
        session, current.tenant_id, cursor=params.cursor, limit=params.limit, status=status
    )
    return map_page(page, AssetRead)


@assets_router.get("/assets/{asset_id}", response_model=AssetRead, dependencies=[_ReadGuard])
async def get_asset(
    asset_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> AssetRead:
    asset = await service.get_asset(session, current.tenant_id, asset_id)
    return AssetRead.model_validate(asset)


# --- Depreciation runs --------------------------------------------------------------


async def _run_inline(
    payload: DepreciationRunRequest,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep,
) -> DepreciationRunRead:
    holder: dict[str, DepreciationRunRead] = {}

    async def work() -> None:
        run = await service.run_depreciation(
            session, current.tenant_id, payload.fiscal_period_id, payload.run_date
        )
        await session.refresh(run)
        holder["read"] = await idem.capture(
            DepreciationRunRead.model_validate(run), status_code=201
        )

    await run_in_uow(session, work)
    return holder["read"]


async def _run_background(
    payload: DepreciationRunRequest,
    current: CurrentUserDep,
    session: SessionDep,
    factory: SessionFactoryDep,
    idem: IdempotentDep,
) -> JobSubmitted:
    holder: dict[str, JobSubmitted] = {}
    job_id_holder: dict[str, uuid.UUID] = {}

    async def work() -> None:
        job = await submit_job(
            session,
            current.tenant_id,
            DEPRECIATION_RUN_JOB,
            {
                "fiscal_period_id": str(payload.fiscal_period_id),
                "run_date": payload.run_date.isoformat(),
            },
            submitted_by=current.user_id,
        )
        job_id_holder["job_id"] = job.id
        holder["read"] = await idem.capture(
            JobSubmitted(job_id=job.id, status=job.status), status_code=202
        )

    await run_in_uow(session, work)
    schedule_job(job_id_holder["job_id"], factory)
    return holder["read"]


@assets_router.post(
    "/depreciation-runs",
    response_model=DepreciationRunRead | JobSubmitted,
    status_code=201,
    dependencies=[Depends(require_permission(FINANCE_DEPRECIATION_RUN))],
)
async def run_depreciation(
    payload: DepreciationRunRequest,
    current: CurrentUserDep,
    session: SessionDep,
    factory: SessionFactoryDep,
    response: Response,
    idem: IdempotentDep = _RunIdempotentDep,
) -> DepreciationRunRead | JobSubmitted:
    """Run depreciation for a period (module docstring): ≤100 eligible assets inline
    (201 run), larger submitted as a background job (202 {job_id}). IDEMPOTENT (D-013)."""
    eligible = await service.count_eligible_assets(
        session, current.tenant_id, payload.fiscal_period_id
    )
    if eligible > DEPRECIATION_RUN_SYNC_MAX_ASSETS:
        response.status_code = 202
        return await _run_background(payload, current, session, factory, idem)
    return await _run_inline(payload, current, session, idem)


@assets_router.get(
    "/depreciation-runs", response_model=Page[DepreciationRunRead], dependencies=[_ReadGuard]
)
async def list_depreciation_runs(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    fiscal_period_id: uuid.UUID | None = None,
) -> Page[DepreciationRunRead]:
    page = await service.list_depreciation_runs(
        session,
        current.tenant_id,
        cursor=params.cursor,
        limit=params.limit,
        fiscal_period_id=fiscal_period_id,
    )
    return map_page(page, DepreciationRunRead)


@assets_router.get(
    "/depreciation-runs/{run_id}",
    response_model=DepreciationRunRead,
    dependencies=[_ReadGuard],
)
async def get_depreciation_run(
    run_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> DepreciationRunRead:
    run = await service.get_depreciation_run(session, current.tenant_id, run_id)
    return DepreciationRunRead.model_validate(run)


@assets_router.get(
    "/depreciation-runs/{run_id}/entries",
    response_model=Page[DepreciationEntryRead],
    dependencies=[_ReadGuard],
)
async def list_depreciation_entries(
    run_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
) -> Page[DepreciationEntryRead]:
    # 404 on an unknown/foreign run (vs a silent empty page); 1 extra query, budget ≤3.
    await service.get_depreciation_run(session, current.tenant_id, run_id)
    page = await service.list_depreciation_entries(
        session, current.tenant_id, run_id, cursor=params.cursor, limit=params.limit
    )
    return map_page(page, DepreciationEntryRead)


@assets_router.get(
    "/asset-register", response_model=AssetRegisterReport, dependencies=[_ReadGuard]
)
async def asset_register(
    as_of: date, current: CurrentUserDep, session: SessionDep
) -> AssetRegisterReport:
    """The register projection as of a date (ONE statement): cost, accumulated depreciation,
    NBV per activated asset — recomputed from the entries, never stored totals."""
    lines = await service.asset_register(session, current.tenant_id, as_of)
    return AssetRegisterReport(
        as_of=as_of,
        items=[
            AssetRegisterRow(
                asset_id=line.asset.id,
                asset_number=line.asset.asset_number,
                name=line.asset.name,
                status=line.asset.status,
                currency_code=line.asset.currency_code,
                acquisition_cost=line.asset.acquisition_cost,
                accumulated_depreciation=line.accumulated_depreciation,
                net_book_value=line.net_book_value,
            )
            for line in lines
        ],
    )
