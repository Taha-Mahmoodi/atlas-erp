"""Quality HTTP layer (thin): parse -> call service -> return schema (PLAN 9.1).

REST under ``/api/v1/quality``: inspection lots (list + point read + the accept/reject usage
decision
+ cancel). There is NO create endpoint — lots come from the goods-receipt handler (a flagged GR line
auto-creates an OPEN lot). Every route is guarded by a quality permission key (D-009); writes commit
through ``run_in_uow`` (D-011) so the decision + its disposition stock move + write-off journal +
audit rows ride the SAME transaction. The decision is IDEMPOTENT (D-013). The list is O(1) queries +
paginated (PERFORMANCE §6).
"""

import uuid

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.quality import service
from app.modules.quality.constants import (
    QUALITY_INSPECTION_DECIDE,
    QUALITY_INSPECTION_MANAGE,
    QUALITY_INSPECTION_READ,
    InspectionLotStatus,
    InspectionSource,
)
from app.modules.quality.schemas import InspectionDecideRequest, InspectionLotRead

router = APIRouter(prefix="/api/v1/quality", tags=["quality"])

_CursorParamsDep = Depends(cursor_params)
_DecideIdem = Depends(Idempotent("quality.inspection.decide"))


@router.get(
    "/inspection-lots",
    response_model=Page[InspectionLotRead],
    dependencies=[Depends(require_permission(QUALITY_INSPECTION_READ))],
)
async def list_inspection_lots(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = _CursorParamsDep,
    status: InspectionLotStatus | None = None,
    item_id: uuid.UUID | None = None,
    source: InspectionSource | None = None,
) -> Page[InspectionLotRead]:
    page = await service.list_inspection_lots(
        session,
        current.tenant_id,
        status=status,
        item_id=item_id,
        source=source,
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, InspectionLotRead)


@router.get(
    "/inspection-lots/{lot_id}",
    response_model=InspectionLotRead,
    dependencies=[Depends(require_permission(QUALITY_INSPECTION_READ))],
)
async def get_inspection_lot(
    lot_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> InspectionLotRead:
    lot = await service.get_inspection_lot(session, current.tenant_id, lot_id)
    return InspectionLotRead.model_validate(lot)


@router.post(
    "/inspection-lots/{lot_id}/decide",
    response_model=InspectionLotRead,
    dependencies=[Depends(require_permission(QUALITY_INSPECTION_DECIDE))],
)
async def decide_inspection_lot(
    lot_id: uuid.UUID,
    payload: InspectionDecideRequest,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _DecideIdem,
) -> InspectionLotRead:
    """Accept/reject an OPEN inspection lot (PLAN 9.1, D-050). A reject dispositions the rejected
    stock via the event bus (SCRAP write-off / BLOCK transfer) — all one transaction; a
    closed-period
    SCRAP rolls the whole decision back. ACCEPTED needs no stock move. IDEMPOTENT (D-013)."""
    holder: dict[str, InspectionLotRead] = {}

    async def work() -> None:
        lot = await service.decide(
            session,
            current.tenant_id,
            lot_id,
            payload,
            decision_by=current.user_id,
        )
        await session.refresh(lot)
        read = InspectionLotRead.model_validate(lot)
        holder["read"] = await idem.capture(read)

    await run_in_uow(session, work)
    return holder["read"]


@router.post(
    "/inspection-lots/{lot_id}/cancel",
    response_model=InspectionLotRead,
    dependencies=[Depends(require_permission(QUALITY_INSPECTION_MANAGE))],
)
async def cancel_inspection_lot(
    lot_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> InspectionLotRead:
    """Cancel an OPEN inspection lot (PLAN 9.1). A decided lot is terminal."""
    holder: dict[str, InspectionLotRead] = {}

    async def work() -> None:
        lot = await service.cancel_lot(session, current.tenant_id, lot_id)
        await session.refresh(lot)
        holder["read"] = InspectionLotRead.model_validate(lot)

    await run_in_uow(session, work)
    return holder["read"]
