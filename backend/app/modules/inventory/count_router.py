"""Inventory physical/cycle count HTTP layer (PLAN 5.4, D-038), included into the inventory router.

A sibling sub-router (the finance journal_router / inventory stock_router precedent), mounted via
``router.include_router(count_router)`` so the module stays ONE surface at ``/api/v1/inventory``.
Covers the count lifecycle: create+snapshot, list, detail, paginated lines, record a counted
quantity, the variance preview, post, cancel.

Permission-guarded (D-009): count.read for the GETs, count.manage for create/record-count/cancel,
count.post for the privileged post (posting variances changes on-hand AND posts GL journals). Writes
commit through ``run_in_uow`` (D-011) so audit + the variance moves' costing journals ride the
transaction. The create and post endpoints are IDEMPOTENT (D-013) — both create stock documents, so
a retried request must not double-snapshot or double-post (``capture()`` lands in the same uow).

The post endpoint backgrounds large counts (PERFORMANCE §3): above ``COUNT_POST_SYNC_MAX_VARIANCES``
snapshot-variance lines it submits an ``inventory.count_post`` job and returns 202 {job_id} for
/api/v1/jobs polling; at or below it posts inline (200). The transactional count/line lists carry NO
ETag (they change as counts are entered — the journal-entry precedent).
"""

import uuid

from fastapi import APIRouter, Depends, Response

from app.core.deps import CurrentUserDep, SessionDep, SessionFactoryDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.jobs import schedule_job, submit_job
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import JobSubmitted, Page
from app.modules.inventory import service
from app.modules.inventory.constants import (
    COUNT_POST_JOB,
    COUNT_POST_SYNC_MAX_VARIANCES,
    INVENTORY_COUNT_MANAGE,
    INVENTORY_COUNT_POST,
    INVENTORY_COUNT_READ,
)
from app.modules.inventory.count_schemas import (
    StockCountCreate,
    StockCountFilter,
    StockCountLineCountUpdate,
    StockCountLineRead,
    StockCountRead,
    StockCountVariancePreview,
)

count_router = APIRouter(tags=["inventory-counts"])

CursorParamsDep = Depends(cursor_params)
_CreateCountIdempotentDep = Depends(Idempotent("inventory.stock_count.create"))
_PostCountIdempotentDep = Depends(Idempotent("inventory.stock_count.post"))


# --- Create + snapshot --------------------------------------------------------


@count_router.post(
    "/stock-counts",
    response_model=StockCountRead,
    status_code=201,
    dependencies=[Depends(require_permission(INVENTORY_COUNT_MANAGE))],
)
async def create_stock_count(
    payload: StockCountCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _CreateCountIdempotentDep,
) -> StockCountRead:
    """Create a count and snapshot its lines (PLAN 5.4). IDEMPOTENT (D-013): a count claims a CNT
    number + registers a document, so a retry must not create a second count or burn a number."""
    holder: dict[str, StockCountRead] = {}

    async def work() -> None:
        count = await service.create_count(session, current.tenant_id, payload)
        await session.refresh(count)
        holder["read"] = await idem.capture(
            StockCountRead.model_validate(count), status_code=201
        )

    await run_in_uow(session, work)
    return holder["read"]


# --- Reads --------------------------------------------------------------------


@count_router.get(
    "/stock-counts",
    response_model=Page[StockCountRead],
    dependencies=[Depends(require_permission(INVENTORY_COUNT_READ))],
)
async def list_stock_counts(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    status: str | None = None,
    warehouse_id: uuid.UUID | None = None,
    count_type: str | None = None,
) -> Page[StockCountRead]:
    """The counts list (PLAN 5.4): keyset-paginated, filtered by status/warehouse/type. No ETag
    (transactional — counts change as quantities are entered, the journal-entry precedent)."""
    filters = StockCountFilter(
        status=status, warehouse_id=warehouse_id, count_type=count_type
    )
    page = await service.list_counts(
        session, current.tenant_id, filters=filters, cursor=params.cursor, limit=params.limit
    )
    return map_page(page, StockCountRead)


@count_router.get(
    "/stock-counts/{count_id}",
    response_model=StockCountRead,
    dependencies=[Depends(require_permission(INVENTORY_COUNT_READ))],
)
async def get_stock_count(
    count_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> StockCountRead:
    count = await service.get_count(session, current.tenant_id, count_id)
    return StockCountRead.model_validate(count)


@count_router.get(
    "/stock-counts/{count_id}/lines",
    response_model=Page[StockCountLineRead],
    dependencies=[Depends(require_permission(INVENTORY_COUNT_READ))],
)
async def list_stock_count_lines(
    count_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
) -> Page[StockCountLineRead]:
    """The lines of a count (PLAN 5.4): keyset-paginated by line number. Separate from the count
    detail so a large physical count's lines page rather than inline (PERFORMANCE §6)."""
    await service.get_count(session, current.tenant_id, count_id)  # 404 if the count is foreign
    page = await service.list_count_lines(
        session, current.tenant_id, count_id, cursor=params.cursor, limit=params.limit
    )
    return map_page(page, StockCountLineRead)


@count_router.get(
    "/stock-counts/{count_id}/variance-preview",
    response_model=StockCountVariancePreview,
    dependencies=[Depends(require_permission(INVENTORY_COUNT_READ))],
)
async def get_stock_count_variance_preview(
    count_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
) -> StockCountVariancePreview:
    """The pre-post variance preview (PLAN 5.4): per-line live-system vs counted vs variance vs
    estimated value impact + the whole-count net total. Lines are keyset-paginated (#78);
    read-only — re-reads live on-hand (the post's authority) with a constant query budget."""
    return await service.variance_preview(
        session, current.tenant_id, count_id, cursor=params.cursor, limit=params.limit
    )


# --- Record counted quantity --------------------------------------------------


@count_router.post(
    "/stock-counts/{count_id}/lines/{line_id}/count",
    response_model=StockCountLineRead,
    dependencies=[Depends(require_permission(INVENTORY_COUNT_MANAGE))],
)
async def record_counted_quantity(
    count_id: uuid.UUID,
    line_id: uuid.UUID,
    payload: StockCountLineCountUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> StockCountLineRead:
    """Record the counted quantity for one line and move the count to COUNTING (PLAN 5.4). Not
    idempotency-keyed: it is a last-write-wins field update, not a document-creating action."""
    holder: dict[str, StockCountLineRead] = {}

    async def work() -> None:
        line = await service.record_counted(
            session, current.tenant_id, count_id, line_id, payload.counted_qty
        )
        await session.refresh(line)
        holder["read"] = StockCountLineRead.model_validate(line)

    await run_in_uow(session, work)
    return holder["read"]


# --- Post + cancel ------------------------------------------------------------


async def _post_inline(
    count_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep,
) -> StockCountRead:
    holder: dict[str, StockCountRead] = {}

    async def work() -> None:
        count = await service.post_count(session, current.tenant_id, count_id)
        await session.refresh(count)
        holder["read"] = await idem.capture(
            StockCountRead.model_validate(count), status_code=200
        )

    await run_in_uow(session, work)
    return holder["read"]


async def _post_background(
    count_id: uuid.UUID,
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
            COUNT_POST_JOB,
            {"count_id": str(count_id)},
            submitted_by=current.user_id,
        )
        job_id_holder["job_id"] = job.id
        holder["read"] = await idem.capture(
            JobSubmitted(job_id=job.id, status=job.status), status_code=202
        )

    await run_in_uow(session, work)
    schedule_job(job_id_holder["job_id"], factory)
    return holder["read"]


@count_router.post(
    "/stock-counts/{count_id}/post",
    response_model=StockCountRead | JobSubmitted,
    dependencies=[Depends(require_permission(INVENTORY_COUNT_POST))],
)
async def post_stock_count(
    count_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    factory: SessionFactoryDep,
    response: Response,
    idem: IdempotentDep = _PostCountIdempotentDep,
) -> StockCountRead | JobSubmitted:
    """Post a count's variances as ADJUSTMENT moves (PLAN 5.4, D-038). ≤
    COUNT_POST_SYNC_MAX_VARIANCES snapshot-variance lines post inline (200 count); larger ones are
    submitted as an ``inventory.count_post`` job (202 {job_id}). IDEMPOTENT (D-013): re-posting a
    POSTED count is rejected by the service, and a replayed key returns the same body."""
    variances = await service.count_variance_estimate(session, current.tenant_id, count_id)
    if variances > COUNT_POST_SYNC_MAX_VARIANCES:
        response.status_code = 202
        return await _post_background(count_id, current, session, factory, idem)
    return await _post_inline(count_id, current, session, idem)


@count_router.post(
    "/stock-counts/{count_id}/cancel",
    response_model=StockCountRead,
    dependencies=[Depends(require_permission(INVENTORY_COUNT_MANAGE))],
)
async def cancel_stock_count(
    count_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> StockCountRead:
    """Cancel a DRAFT/COUNTING count (PLAN 5.4). A POSTED count is terminal — its variances are real
    moves, so corrections are new counts/adjustments (409 inventory.count_not_cancellable)."""
    holder: dict[str, StockCountRead] = {}

    async def work() -> None:
        count = await service.cancel_count(session, current.tenant_id, count_id)
        await session.refresh(count)
        holder["read"] = StockCountRead.model_validate(count)

    await run_in_uow(session, work)
    return holder["read"]
