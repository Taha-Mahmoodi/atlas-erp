"""Sales-quotation HTTP layer (PLAN 7.2), included into the sales router.

A sibling router under the same ``/api/v1/sales`` prefix, mounted by ``router.include_router`` in
router.py (the procurement po_router/sub-router precedent — ONE module surface, no second mount in
main.py). Reads guarded by ``sales.quote.read``; create/edit/send/accept/reject/cancel by
``sales.quote.manage`` (a quote carries no committing gate, so MANAGE covers every action). Writes
commit through ``run_in_uow`` (D-011); the document-creating + send/accept/reject endpoints are
IDEMPOTENT (D-013). List reads call the lazy-expiry sweep so a lapsed quote shows EXPIRED.
"""

import uuid

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.sales import service
from app.modules.sales.constants import (
    SALES_QUOTE_MANAGE,
    SALES_QUOTE_READ,
)
from app.modules.sales.schemas import (
    QuoteCreate,
    QuoteDetail,
    QuoteLineRead,
    QuoteRead,
    QuoteUpdate,
)

quote_router = APIRouter(tags=["sales-quotes"])

CursorParamsDep = Depends(cursor_params)
_CreateIdem = Depends(Idempotent("sales.quote.create"))
_SendIdem = Depends(Idempotent("sales.quote.send"))
_AcceptIdem = Depends(Idempotent("sales.quote.accept"))
_RejectIdem = Depends(Idempotent("sales.quote.reject"))


async def quote_detail(
    session: SessionDep, tenant_id: uuid.UUID, quote_id: uuid.UUID
) -> QuoteDetail:
    quote = await service.get_quote(session, tenant_id, quote_id)
    await session.refresh(quote)
    lines = await service.get_quote_lines(session, tenant_id, quote_id)
    header = QuoteRead.model_validate(quote)
    return QuoteDetail(
        **header.model_dump(),
        lines=[QuoteLineRead.model_validate(line) for line in lines],
    )


@quote_router.post(
    "/quotes",
    response_model=QuoteDetail,
    status_code=201,
    dependencies=[Depends(require_permission(SALES_QUOTE_MANAGE))],
)
async def create_quote(
    payload: QuoteCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _CreateIdem,
) -> QuoteDetail:
    """Create a DRAFT quote (PLAN 7.2): customer must exist; lines priced from the resolver +
    discounts. IDEMPOTENT (D-013)."""
    holder: dict[str, QuoteDetail] = {}

    async def work() -> None:
        quote = await service.create_quote(session, current.tenant_id, payload)
        detail = await quote_detail(session, current.tenant_id, quote.id)
        holder["read"] = await idem.capture(detail, status_code=201)

    await run_in_uow(session, work)
    return holder["read"]


@quote_router.get(
    "/quotes",
    response_model=Page[QuoteRead],
    dependencies=[Depends(require_permission(SALES_QUOTE_READ))],
)
async def list_quotes(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    status: str | None = None,
    customer_id: uuid.UUID | None = None,
) -> Page[QuoteRead]:
    page = await service.list_quotes(
        session,
        current.tenant_id,
        status=status,
        customer_id=customer_id,
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, QuoteRead)


@quote_router.get(
    "/quotes/{quote_id}",
    response_model=QuoteDetail,
    dependencies=[Depends(require_permission(SALES_QUOTE_READ))],
)
async def get_quote(
    quote_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> QuoteDetail:
    """Read a quote + lines (PLAN 7.2). Applies the lazy-expiry check (a lapsed open quote is moved
    to EXPIRED on access) inside a uow so the status reflects validity."""
    holder: dict[str, QuoteDetail] = {}

    async def work() -> None:
        quote = await service.get_quote(session, current.tenant_id, quote_id)
        await service.mark_expired_if_lapsed(session, current.tenant_id, quote)
        holder["read"] = await quote_detail(session, current.tenant_id, quote_id)

    await run_in_uow(session, work)
    return holder["read"]


@quote_router.patch(
    "/quotes/{quote_id}",
    response_model=QuoteDetail,
    dependencies=[Depends(require_permission(SALES_QUOTE_MANAGE))],
)
async def update_quote(
    quote_id: uuid.UUID,
    payload: QuoteUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> QuoteDetail:
    holder: dict[str, QuoteDetail] = {}

    async def work() -> None:
        await service.update_quote(session, current.tenant_id, quote_id, payload)
        holder["read"] = await quote_detail(session, current.tenant_id, quote_id)

    await run_in_uow(session, work)
    return holder["read"]


@quote_router.post(
    "/quotes/{quote_id}/send",
    response_model=QuoteDetail,
    dependencies=[Depends(require_permission(SALES_QUOTE_MANAGE))],
)
async def send_quote(
    quote_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _SendIdem,
) -> QuoteDetail:
    """Issue a DRAFT quote to the customer (DRAFT→SENT). IDEMPOTENT (D-013)."""
    holder: dict[str, QuoteDetail] = {}

    async def work() -> None:
        await service.send_quote(session, current.tenant_id, quote_id)
        detail = await quote_detail(session, current.tenant_id, quote_id)
        holder["read"] = await idem.capture(detail)

    await run_in_uow(session, work)
    return holder["read"]


@quote_router.post(
    "/quotes/{quote_id}/accept",
    response_model=QuoteDetail,
    dependencies=[Depends(require_permission(SALES_QUOTE_MANAGE))],
)
async def accept_quote(
    quote_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _AcceptIdem,
) -> QuoteDetail:
    """Record acceptance (SENT→ACCEPTED) — the only state convertible to an order. IDEMPOTENT."""
    holder: dict[str, QuoteDetail] = {}

    async def work() -> None:
        await service.accept_quote(session, current.tenant_id, quote_id)
        detail = await quote_detail(session, current.tenant_id, quote_id)
        holder["read"] = await idem.capture(detail)

    await run_in_uow(session, work)
    return holder["read"]


@quote_router.post(
    "/quotes/{quote_id}/reject",
    response_model=QuoteDetail,
    dependencies=[Depends(require_permission(SALES_QUOTE_MANAGE))],
)
async def reject_quote(
    quote_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _RejectIdem,
) -> QuoteDetail:
    """Record rejection (SENT→REJECTED); terminal. IDEMPOTENT (D-013)."""
    holder: dict[str, QuoteDetail] = {}

    async def work() -> None:
        await service.reject_quote(session, current.tenant_id, quote_id)
        detail = await quote_detail(session, current.tenant_id, quote_id)
        holder["read"] = await idem.capture(detail)

    await run_in_uow(session, work)
    return holder["read"]


@quote_router.post(
    "/quotes/{quote_id}/cancel",
    response_model=QuoteDetail,
    dependencies=[Depends(require_permission(SALES_QUOTE_MANAGE))],
)
async def cancel_quote(
    quote_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> QuoteDetail:
    holder: dict[str, QuoteDetail] = {}

    async def work() -> None:
        await service.cancel_quote(session, current.tenant_id, quote_id)
        holder["read"] = await quote_detail(session, current.tenant_id, quote_id)

    await run_in_uow(session, work)
    return holder["read"]
