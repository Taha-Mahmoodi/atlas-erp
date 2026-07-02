"""Purchase-requisition HTTP layer (PLAN 6.2), included into the procurement router.

Split out of router.py the way finance's ap_router/ar_router are: mounted via
``router.include_router(requisition_router)`` so the module stays ONE surface at
``/api/v1/procurement`` — no second mount in main.py. Reads are guarded by
``procurement.requisition.read``; create/edit/submit/convert/cancel by
``procurement.requisition.manage``; approve/reject by the distinct
``procurement.requisition.approve`` key. Writes commit through ``run_in_uow`` (D-011) so audit rows
ride the transaction; the document-creating + convert + approve endpoints are IDEMPOTENT (D-013).
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
    PROCUREMENT_REQUISITION_APPROVE,
    PROCUREMENT_REQUISITION_MANAGE,
    PROCUREMENT_REQUISITION_READ,
    ApprovalDecision,
)
from app.modules.procurement.po_router import po_detail
from app.modules.procurement.rfq_router import rfq_detail
from app.modules.procurement.schemas import (
    ApprovalDecisionPayload,
    PurchaseOrderDetail,
    PurchaseOrderFromRequisition,
    RequisitionCreate,
    RequisitionDetail,
    RequisitionLineRead,
    RequisitionRead,
    RequisitionUpdate,
    RfqDetail,
    RfqFromRequisition,
)

requisition_router = APIRouter(tags=["procurement-requisitions"])

CursorParamsDep = Depends(cursor_params)
_CreateIdem = Depends(Idempotent("procurement.requisition.create"))
_SubmitIdem = Depends(Idempotent("procurement.requisition.submit"))
_DecideIdem = Depends(Idempotent("procurement.requisition.decide"))
_ToRfqIdem = Depends(Idempotent("procurement.requisition.to_rfq"))
_ToPoIdem = Depends(Idempotent("procurement.requisition.to_po"))


async def requisition_detail(
    session: SessionDep, tenant_id: uuid.UUID, requisition_id: uuid.UUID
) -> RequisitionDetail:
    """Load a requisition + its lines into the detail schema. ``refresh`` materializes server
    defaults in the async context before the sync ``model_validate``."""
    req = await service.get_requisition(session, tenant_id, requisition_id)
    await session.refresh(req)
    lines = await service.get_requisition_lines(session, tenant_id, requisition_id)
    header = RequisitionRead.model_validate(req)
    return RequisitionDetail(
        **header.model_dump(),
        lines=[RequisitionLineRead.model_validate(line) for line in lines],
    )


@requisition_router.post(
    "/requisitions",
    response_model=RequisitionDetail,
    status_code=201,
    dependencies=[Depends(require_permission(PROCUREMENT_REQUISITION_MANAGE))],
)
async def create_requisition(
    payload: RequisitionCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _CreateIdem,
) -> RequisitionDetail:
    """Create a DRAFT requisition (PLAN 6.2). IDEMPOTENT (D-013): capture lands in the creating
    uow, so the document + replay record commit atomically."""
    holder: dict[str, RequisitionDetail] = {}

    async def work() -> None:
        req = await service.create_requisition(session, current.tenant_id, payload)
        detail = await requisition_detail(session, current.tenant_id, req.id)
        holder["read"] = await idem.capture(detail, status_code=201)

    await run_in_uow(session, work)
    return holder["read"]


@requisition_router.get(
    "/requisitions",
    response_model=Page[RequisitionRead],
    dependencies=[Depends(require_permission(PROCUREMENT_REQUISITION_READ))],
)
async def list_requisitions(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    status: str | None = None,
    requested_by: uuid.UUID | None = None,
) -> Page[RequisitionRead]:
    page = await service.list_requisitions(
        session,
        current.tenant_id,
        status=status,
        requested_by=requested_by,
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, RequisitionRead)


@requisition_router.get(
    "/requisitions/{requisition_id}",
    response_model=RequisitionDetail,
    dependencies=[Depends(require_permission(PROCUREMENT_REQUISITION_READ))],
)
async def get_requisition(
    requisition_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> RequisitionDetail:
    return await requisition_detail(session, current.tenant_id, requisition_id)


@requisition_router.patch(
    "/requisitions/{requisition_id}",
    response_model=RequisitionDetail,
    dependencies=[Depends(require_permission(PROCUREMENT_REQUISITION_MANAGE))],
)
async def update_requisition(
    requisition_id: uuid.UUID,
    payload: RequisitionUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> RequisitionDetail:
    holder: dict[str, RequisitionDetail] = {}

    async def work() -> None:
        await service.update_requisition(session, current.tenant_id, requisition_id, payload)
        holder["read"] = await requisition_detail(session, current.tenant_id, requisition_id)

    await run_in_uow(session, work)
    return holder["read"]


@requisition_router.post(
    "/requisitions/{requisition_id}/submit",
    response_model=RequisitionDetail,
    dependencies=[Depends(require_permission(PROCUREMENT_REQUISITION_MANAGE))],
)
async def submit_requisition(
    requisition_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _SubmitIdem,
) -> RequisitionDetail:
    """Submit a DRAFT requisition (PLAN 6.2): the approval-threshold rule decides SUBMITTED vs auto
    APPROVED. IDEMPOTENT (D-013)."""
    holder: dict[str, RequisitionDetail] = {}

    async def work() -> None:
        await service.submit_requisition(session, current.tenant_id, requisition_id)
        detail = await requisition_detail(session, current.tenant_id, requisition_id)
        holder["read"] = await idem.capture(detail)

    await run_in_uow(session, work)
    return holder["read"]


@requisition_router.post(
    "/requisitions/{requisition_id}/decision",
    response_model=RequisitionDetail,
    dependencies=[Depends(require_permission(PROCUREMENT_REQUISITION_APPROVE))],
)
async def decide_requisition(
    requisition_id: uuid.UUID,
    payload: ApprovalDecisionPayload,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _DecideIdem,
) -> RequisitionDetail:
    """Approve or reject a SUBMITTED requisition (PLAN 6.2, the procurement.requisition.approve
    action). IDEMPOTENT (D-013)."""
    holder: dict[str, RequisitionDetail] = {}

    async def work() -> None:
        await service.decide_requisition(
            session,
            current.tenant_id,
            requisition_id,
            approved=ApprovalDecision(payload.decision) == ApprovalDecision.APPROVED,
        )
        detail = await requisition_detail(session, current.tenant_id, requisition_id)
        holder["read"] = await idem.capture(detail)

    await run_in_uow(session, work)
    return holder["read"]


@requisition_router.post(
    "/requisitions/{requisition_id}/cancel",
    response_model=RequisitionDetail,
    dependencies=[Depends(require_permission(PROCUREMENT_REQUISITION_MANAGE))],
)
async def cancel_requisition(
    requisition_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> RequisitionDetail:
    holder: dict[str, RequisitionDetail] = {}

    async def work() -> None:
        await service.cancel_requisition(session, current.tenant_id, requisition_id)
        holder["read"] = await requisition_detail(session, current.tenant_id, requisition_id)

    await run_in_uow(session, work)
    return holder["read"]


@requisition_router.post(
    "/requisitions/{requisition_id}/convert-to-rfq",
    response_model=RfqDetail,
    status_code=201,
    dependencies=[Depends(require_permission(PROCUREMENT_REQUISITION_MANAGE))],
)
async def convert_requisition_to_rfq(
    requisition_id: uuid.UUID,
    payload: RfqFromRequisition,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _ToRfqIdem,
) -> RfqDetail:
    """Source an APPROVED requisition into an RFQ (PLAN 6.2): copies lines + links docflow.
    IDEMPOTENT (D-013)."""
    holder: dict[str, RfqDetail] = {}

    async def work() -> None:
        rfq = await service.convert_requisition_to_rfq(
            session, current.tenant_id, requisition_id, payload
        )
        detail = await rfq_detail(session, current.tenant_id, rfq.id)
        holder["read"] = await idem.capture(detail, status_code=201)

    await run_in_uow(session, work)
    return holder["read"]


@requisition_router.post(
    "/requisitions/{requisition_id}/convert-to-po",
    response_model=PurchaseOrderDetail,
    status_code=201,
    dependencies=[Depends(require_permission(PROCUREMENT_REQUISITION_MANAGE))],
)
async def convert_requisition_to_po(
    requisition_id: uuid.UUID,
    payload: PurchaseOrderFromRequisition,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _ToPoIdem,
) -> PurchaseOrderDetail:
    """Order an APPROVED requisition straight into a PO (PLAN 6.2): copies lines + links docflow.
    IDEMPOTENT (D-013)."""
    holder: dict[str, PurchaseOrderDetail] = {}

    async def work() -> None:
        po = await service.convert_requisition_to_po(
            session, current.tenant_id, requisition_id, payload
        )
        detail = await po_detail(session, current.tenant_id, po.id)
        holder["read"] = await idem.capture(detail, status_code=201)

    await run_in_uow(session, work)
    return holder["read"]
