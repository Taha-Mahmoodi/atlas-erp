"""Multi-currency HTTP layer (D-019), included into the finance router.

Split out of router.py to keep both files under the STRUCTURE §3 400-line cap (the finance router
covers accounts/periods/journal; this sub-router covers FX). Mounted via
``router.include_router(fx_router)`` in router.py, so the whole module is still ONE surface at
``/api/v1/finance`` — there is no second mount in main.py.

Currencies, exchange rates and posting-defaults are guarded by ``finance.fx.manage``; running a
revaluation is guarded by ``finance.fx.revalue`` and is IDEMPOTENT (D-013 — it posts financial
documents). Writes commit through ``run_in_uow`` (D-011) so audit + events ride the transaction.
"""

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.pagination import CursorParams, cursor_params
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.finance import service
from app.modules.finance.constants import (
    FINANCE_FX_MANAGE,
    FINANCE_FX_REVALUE,
    RateKind,
)
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
    response_model=list[CurrencyRead],
    dependencies=[Depends(require_permission(FINANCE_FX_MANAGE))],
)
async def list_currencies(
    current: CurrentUserDep, session: SessionDep
) -> list[CurrencyRead]:
    currencies = await service.list_currencies(session, current.tenant_id)
    return [CurrencyRead.model_validate(c) for c in currencies]


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
    return Page(
        items=[ExchangeRateRead.model_validate(item) for item in page.items],
        next_cursor=page.next_cursor,
        limit=page.limit,
    )


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
    response_model=list[PostingDefaultRead],
    dependencies=[Depends(require_permission(FINANCE_FX_MANAGE))],
)
async def list_posting_defaults(
    current: CurrentUserDep, session: SessionDep
) -> list[PostingDefaultRead]:
    defaults = await service.list_posting_defaults(session, current.tenant_id)
    return [PostingDefaultRead.model_validate(d) for d in defaults]


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
    response_model=list[FxRevaluationRunRead],
    dependencies=[Depends(require_permission(FINANCE_FX_REVALUE))],
)
async def list_fx_revaluation_runs(
    current: CurrentUserDep, session: SessionDep
) -> list[FxRevaluationRunRead]:
    runs = await service.list_revaluation_runs(session, current.tenant_id)
    return [FxRevaluationRunRead.model_validate(run) for run in runs]


@fx_router.post(
    "/fx-revaluation-runs",
    response_model=FxRevaluationRunRead,
    status_code=201,
    dependencies=[Depends(require_permission(FINANCE_FX_REVALUE))],
)
async def run_fx_revaluation(
    payload: FxRevaluationRunRequest,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _RevalueIdempotentDep,
) -> FxRevaluationRunRead:
    """Run unrealized-FX revaluation (D-019). IDEMPOTENT (D-013): it posts FX_REVAL documents +
    auto-reversals, so a retried request must not double-post — capture() lands in the same uow."""
    holder: dict[str, FxRevaluationRunRead] = {}

    async def work() -> None:
        run = await service.run_fx_revaluation(
            session, current.tenant_id, payload.fiscal_period_id, payload.rate_date
        )
        await session.refresh(run)
        holder["read"] = await idem.capture(
            FxRevaluationRunRead.model_validate(run), status_code=201
        )

    await run_in_uow(session, work)
    return holder["read"]
