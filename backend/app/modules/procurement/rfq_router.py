"""RFQ HTTP layer (PLAN 6.2), included into the procurement router.

Reads guarded by ``procurement.rfq.read``; create/send/record-quote/close/convert by
``procurement.rfq.manage`` (an RFQ has no separate approve gate — sourcing is not committing). The
convert-from-requisition action lives on the requisition router (it starts from the requisition);
the convert-to-PO action lives on the PO router. Writes commit through ``run_in_uow`` (D-011); the
document-creating + send + record-quote endpoints are IDEMPOTENT (D-013).
"""

import uuid

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.procurement import service
from app.modules.procurement.constants import (
    PROCUREMENT_RFQ_MANAGE,
    PROCUREMENT_RFQ_READ,
)
from app.modules.procurement.schemas import (
    RecordQuotePayload,
    RfqCreate,
    RfqDetail,
    RfqLineRead,
    RfqRead,
)

rfq_router = APIRouter(tags=["procurement-rfqs"])

CursorParamsDep = Depends(cursor_params)
_CreateIdem = Depends(Idempotent("procurement.rfq.create"))
_SendIdem = Depends(Idempotent("procurement.rfq.send"))
_QuoteIdem = Depends(Idempotent("procurement.rfq.quote"))


async def rfq_detail(
    session: SessionDep, tenant_id: uuid.UUID, rfq_id: uuid.UUID
) -> RfqDetail:
    rfq = await service.get_rfq(session, tenant_id, rfq_id)
    await session.refresh(rfq)
    lines = await service.get_rfq_lines(session, tenant_id, rfq_id)
    header = RfqRead.model_validate(rfq)
    return RfqDetail(
        **header.model_dump(),
        lines=[RfqLineRead.model_validate(line) for line in lines],
    )


@rfq_router.post(
    "/rfqs",
    response_model=RfqDetail,
    status_code=201,
    dependencies=[Depends(require_permission(PROCUREMENT_RFQ_MANAGE))],
)
async def create_rfq(
    payload: RfqCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _CreateIdem,
) -> RfqDetail:
    """Create a DRAFT RFQ from scratch (PLAN 6.2). IDEMPOTENT (D-013)."""
    holder: dict[str, RfqDetail] = {}

    async def work() -> None:
        rfq = await service.create_rfq(session, current.tenant_id, payload)
        detail = await rfq_detail(session, current.tenant_id, rfq.id)
        holder["read"] = await idem.capture(detail, status_code=201)

    await run_in_uow(session, work)
    return holder["read"]


@rfq_router.get(
    "/rfqs",
    response_model=Page[RfqRead],
    dependencies=[Depends(require_permission(PROCUREMENT_RFQ_READ))],
)
async def list_rfqs(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    status: str | None = None,
    vendor_id: uuid.UUID | None = None,
) -> Page[RfqRead]:
    page = await service.list_rfqs(
        session,
        current.tenant_id,
        status=status,
        vendor_id=vendor_id,
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, RfqRead)


@rfq_router.get(
    "/rfqs/{rfq_id}",
    response_model=RfqDetail,
    dependencies=[Depends(require_permission(PROCUREMENT_RFQ_READ))],
)
async def get_rfq(
    rfq_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> RfqDetail:
    return await rfq_detail(session, current.tenant_id, rfq_id)


@rfq_router.post(
    "/rfqs/{rfq_id}/send",
    response_model=RfqDetail,
    dependencies=[Depends(require_permission(PROCUREMENT_RFQ_MANAGE))],
)
async def send_rfq(
    rfq_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _SendIdem,
) -> RfqDetail:
    """Issue a DRAFT RFQ to its vendor (PLAN 6.2): DRAFT→SENT. IDEMPOTENT (D-013)."""
    holder: dict[str, RfqDetail] = {}

    async def work() -> None:
        await service.send_rfq(session, current.tenant_id, rfq_id)
        detail = await rfq_detail(session, current.tenant_id, rfq_id)
        holder["read"] = await idem.capture(detail)

    await run_in_uow(session, work)
    return holder["read"]


@rfq_router.post(
    "/rfqs/{rfq_id}/record-quote",
    response_model=RfqDetail,
    dependencies=[Depends(require_permission(PROCUREMENT_RFQ_MANAGE))],
)
async def record_quote(
    rfq_id: uuid.UUID,
    payload: RecordQuotePayload,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _QuoteIdem,
) -> RfqDetail:
    """Record the vendor's quote on a SENT RFQ (PLAN 6.2): SENT→QUOTED. IDEMPOTENT (D-013)."""
    holder: dict[str, RfqDetail] = {}

    async def work() -> None:
        await service.record_quote(session, current.tenant_id, rfq_id, payload)
        detail = await rfq_detail(session, current.tenant_id, rfq_id)
        holder["read"] = await idem.capture(detail)

    await run_in_uow(session, work)
    return holder["read"]


@rfq_router.post(
    "/rfqs/{rfq_id}/close",
    response_model=RfqDetail,
    dependencies=[Depends(require_permission(PROCUREMENT_RFQ_MANAGE))],
)
async def close_rfq(
    rfq_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> RfqDetail:
    holder: dict[str, RfqDetail] = {}

    async def work() -> None:
        await service.close_rfq(session, current.tenant_id, rfq_id)
        holder["read"] = await rfq_detail(session, current.tenant_id, rfq_id)

    await run_in_uow(session, work)
    return holder["read"]
