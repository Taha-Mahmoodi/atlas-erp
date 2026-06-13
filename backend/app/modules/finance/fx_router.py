"""Multi-currency HTTP layer (D-019), included into the finance router.

Split out of router.py to keep both files under the STRUCTURE §3 400-line cap (the finance router
covers accounts/periods/journal; this sub-router covers FX). Mounted via
``router.include_router(fx_router)`` in router.py, so the whole module is still ONE surface at
``/api/v1/finance`` — there is no second mount in main.py.

Currencies, exchange rates and posting-defaults are guarded by ``finance.fx.manage``; running a
revaluation is guarded by ``finance.fx.revalue`` and is IDEMPOTENT (D-013 — it posts financial
documents). Writes commit through ``run_in_uow`` (D-011) so audit + events ride the transaction.
"""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, Request, Response

from app.core.conditional import (
    collection_etag,
    conditional_response,
    request_fingerprint,
)
from app.core.deps import CurrentUserDep, SessionDep, SessionFactoryDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.jobs import schedule_job, submit_job
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import JobSubmitted, Page
from app.modules.finance import service
from app.modules.finance.constants import (
    FINANCE_FX_MANAGE,
    FINANCE_FX_REVALUE,
    FX_REVALUATION_JOB,
    RateKind,
)
from app.modules.finance.models import Currency, PostingDefault
from app.modules.finance.schemas import (
    CurrencyCreate,
    CurrencyRead,
    ExchangeRateCreate,
    ExchangeRateRead,
    FxRevaluationRunRead,
    FxRevaluationRunRequest,
    PostingDefaultRead,
    PostingDefaultSet,
)

fx_router = APIRouter(tags=["finance-fx"])

CursorParamsDep = Depends(cursor_params)
_RevalueIdempotentDep = Depends(Idempotent("finance.fx.revalue"))


async def _commit[T](session: SessionDep, work: Callable[[], Awaitable[T]]) -> T:
    """Run a service call inside the D-011 uow and return its ORM result, refreshing it inside the
    work so server defaults materialize in the async context (same pattern as the finance router's
    _commit; duplicated here rather than cross-imported to keep the sub-router self-contained)."""
    holder: list[T] = []

    async def _work() -> None:
        result = await work()
        await session.refresh(result)
        holder.append(result)

    await run_in_uow(session, _work)
    return holder[0]


# --- Currencies ---------------------------------------------------------------


@fx_router.get(
    "/currencies",
    response_model=Page[CurrencyRead],
    dependencies=[Depends(require_permission(FINANCE_FX_MANAGE))],
)
async def list_currencies(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
) -> Page[CurrencyRead] | Response:
    """Conditional-GET supported (D-035): collection ETag over the tenant's currencies."""
    fingerprint = request_fingerprint(params.cursor, params.limit)
    etag = await collection_etag(session, Currency, request_fingerprint=fingerprint)

    async def builder() -> Page[CurrencyRead]:
        page = await service.list_currencies(
            session, current.tenant_id, cursor=params.cursor, limit=params.limit
        )
        return map_page(page, CurrencyRead)

    return await conditional_response(request, response, etag, builder)


@fx_router.post(
    "/currencies",
    response_model=CurrencyRead,
    status_code=201,
    dependencies=[Depends(require_permission(FINANCE_FX_MANAGE))],
)
async def create_currency(
    payload: CurrencyCreate, current: CurrentUserDep, session: SessionDep
) -> CurrencyRead:
    currency = await _commit(
        session,
        lambda: service.create_currency(
            session,
            current.tenant_id,
            code=payload.code,
            name=payload.name,
            decimal_places=payload.decimal_places,
            is_functional=payload.is_functional,
        ),
    )
    return CurrencyRead.model_validate(currency)


# --- Exchange rates -----------------------------------------------------------


@fx_router.get(
    "/exchange-rates",
    response_model=Page[ExchangeRateRead],
    dependencies=[Depends(require_permission(FINANCE_FX_MANAGE))],
)
async def list_exchange_rates(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    from_currency_code: str | None = None,
    to_currency_code: str | None = None,
    rate_type: str | None = None,
) -> Page[ExchangeRateRead]:
    page = await service.list_exchange_rates(
        session,
        current.tenant_id,
        cursor=params.cursor,
        limit=params.limit,
        from_currency_code=from_currency_code,
        to_currency_code=to_currency_code,
        rate_type=RateKind(rate_type) if rate_type is not None else None,
    )
    return map_page(page, ExchangeRateRead)


@fx_router.post(
    "/exchange-rates",
    response_model=ExchangeRateRead,
    status_code=201,
    dependencies=[Depends(require_permission(FINANCE_FX_MANAGE))],
)
async def create_exchange_rate(
    payload: ExchangeRateCreate, current: CurrentUserDep, session: SessionDep
) -> ExchangeRateRead:
    rate = await _commit(
        session,
        lambda: service.create_exchange_rate(
            session,
            current.tenant_id,
            rate_date=payload.rate_date,
            from_currency_code=payload.from_currency_code,
            to_currency_code=payload.to_currency_code,
            rate=payload.rate,
            rate_type=payload.rate_type,
        ),
    )
    return ExchangeRateRead.model_validate(rate)


# --- Posting defaults ---------------------------------------------------------


@fx_router.get(
    "/posting-defaults",
    response_model=Page[PostingDefaultRead],
    dependencies=[Depends(require_permission(FINANCE_FX_MANAGE))],
)
async def list_posting_defaults(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
) -> Page[PostingDefaultRead] | Response:
    """Conditional-GET supported (D-035): collection ETag over the posting-default settings."""
    fingerprint = request_fingerprint(params.cursor, params.limit)
    etag = await collection_etag(session, PostingDefault, request_fingerprint=fingerprint)

    async def builder() -> Page[PostingDefaultRead]:
        page = await service.list_posting_defaults(
            session, current.tenant_id, cursor=params.cursor, limit=params.limit
        )
        return map_page(page, PostingDefaultRead)

    return await conditional_response(request, response, etag, builder)


@fx_router.put(
    "/posting-defaults",
    response_model=PostingDefaultRead,
    dependencies=[Depends(require_permission(FINANCE_FX_MANAGE))],
)
async def set_posting_default(
    payload: PostingDefaultSet, current: CurrentUserDep, session: SessionDep
) -> PostingDefaultRead:
    default = await _commit(
        session,
        lambda: service.set_posting_default(
            session, current.tenant_id, payload.purpose, payload.account_id
        ),
    )
    return PostingDefaultRead.model_validate(default)


# --- Revaluation runs ---------------------------------------------------------


@fx_router.get(
    "/fx-revaluation-runs",
    response_model=Page[FxRevaluationRunRead],
    dependencies=[Depends(require_permission(FINANCE_FX_REVALUE))],
)
async def list_fx_revaluation_runs(
    current: CurrentUserDep, session: SessionDep, params: CursorParams = CursorParamsDep
) -> Page[FxRevaluationRunRead]:
    page = await service.list_revaluation_runs(
        session, current.tenant_id, cursor=params.cursor, limit=params.limit
    )
    return map_page(page, FxRevaluationRunRead)


@fx_router.post(
    "/fx-revaluation-runs",
    response_model=JobSubmitted,
    status_code=202,
    dependencies=[Depends(require_permission(FINANCE_FX_REVALUE))],
)
async def run_fx_revaluation(
    payload: FxRevaluationRunRequest,
    current: CurrentUserDep,
    session: SessionDep,
    factory: SessionFactoryDep,
    idem: IdempotentDep = _RevalueIdempotentDep,
) -> JobSubmitted:
    """Submit an unrealized-FX revaluation as a background job (PERFORMANCE §3, closes #26):
    returns 202 {job_id}; poll /api/v1/jobs/{job_id} for the run outcome. IDEMPOTENT (D-013):
    the capture lands in the same uow as the PENDING row, so a retried request replays the SAME
    job id instead of submitting a second run. Scheduled strictly AFTER the uow commit."""
    holder: dict[str, JobSubmitted] = {}
    job_id_holder: dict[str, uuid.UUID] = {}

    async def work() -> None:
        job = await submit_job(
            session,
            current.tenant_id,
            FX_REVALUATION_JOB,
            {
                "fiscal_period_id": str(payload.fiscal_period_id),
                "rate_date": payload.rate_date.isoformat(),
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
