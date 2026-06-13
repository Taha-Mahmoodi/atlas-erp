"""Invoice-match + reorder-scan HTTP layer (PLAN 6.4, D-042), included into the procurement router.

Reads guarded by ``procurement.invoice_match.read``; create/override/cancel the match + the
tolerance config by ``procurement.invoice_match.manage``; the POST action (create + post the AP
vendor bill via the event bus) by the distinct ``procurement.invoice_match.post`` key (the
journal.post / goods_receipt.post precedent — building a document and committing it are separate
rights). The reorder scan rides ``procurement.requisition.manage`` (it CREATES a draft requisition).
Writes commit through ``run_in_uow`` (D-011) so the match + its AP bill + the PO update commit (or
roll back)
atomically; the document-creating + post + scan endpoints are IDEMPOTENT (D-013). The list is O(1)
queries + paginated (PERFORMANCE §6).
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
    PROCUREMENT_INVOICE_MATCH_MANAGE,
    PROCUREMENT_INVOICE_MATCH_POST,
    PROCUREMENT_INVOICE_MATCH_READ,
    PROCUREMENT_REQUISITION_MANAGE,
)
from app.modules.procurement.schemas import (
    InvoiceMatchCreate,
    InvoiceMatchDetail,
    InvoiceMatchLineRead,
    InvoiceMatchRead,
    MatchToleranceRead,
    MatchToleranceUpsert,
    RequisitionDetail,
    RequisitionRead,
)

invoice_match_router = APIRouter(tags=["procurement-invoice-matches"])

CursorParamsDep = Depends(cursor_params)
_CreateIdem = Depends(Idempotent("procurement.invoice_match.create"))
_PostIdem = Depends(Idempotent("procurement.invoice_match.post"))
_ScanIdem = Depends(Idempotent("procurement.reorder_scan"))


async def match_detail(
    session: SessionDep, tenant_id: uuid.UUID, match_id: uuid.UUID
) -> InvoiceMatchDetail:
    match = await service.get_invoice_match(session, tenant_id, match_id)
    await session.refresh(match)
    lines = await service.get_invoice_match_lines(session, tenant_id, match_id)
    header = InvoiceMatchRead.model_validate(match)
    return InvoiceMatchDetail(
        **header.model_dump(),
        lines=[InvoiceMatchLineRead.model_validate(line) for line in lines],
    )


@invoice_match_router.post(
    "/invoice-matches",
    response_model=InvoiceMatchDetail,
    status_code=201,
    dependencies=[Depends(require_permission(PROCUREMENT_INVOICE_MATCH_MANAGE))],
)
async def create_invoice_match(
    payload: InvoiceMatchCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _CreateIdem,
) -> InvoiceMatchDetail:
    """Create a DRAFT 3-way match against a received PO (PLAN 6.4): over-billing beyond received →
    422; within tolerance → MATCHED, exceeding it → EXCEPTION. IDEMPOTENT (D-013)."""
    holder: dict[str, InvoiceMatchDetail] = {}

    async def work() -> None:
        match = await service.create_invoice_match(session, current.tenant_id, payload)
        detail = await match_detail(session, current.tenant_id, match.id)
        holder["read"] = await idem.capture(detail, status_code=201)

    await run_in_uow(session, work)
    return holder["read"]


@invoice_match_router.get(
    "/invoice-matches",
    response_model=Page[InvoiceMatchRead],
    dependencies=[Depends(require_permission(PROCUREMENT_INVOICE_MATCH_READ))],
)
async def list_invoice_matches(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    purchase_order_id: uuid.UUID | None = None,
    status: str | None = None,
) -> Page[InvoiceMatchRead]:
    page = await service.list_invoice_matches(
        session,
        current.tenant_id,
        purchase_order_id=purchase_order_id,
        status=status,
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, InvoiceMatchRead)


@invoice_match_router.get(
    "/invoice-matches/{match_id}",
    response_model=InvoiceMatchDetail,
    dependencies=[Depends(require_permission(PROCUREMENT_INVOICE_MATCH_READ))],
)
async def get_invoice_match(
    match_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> InvoiceMatchDetail:
    return await match_detail(session, current.tenant_id, match_id)


@invoice_match_router.post(
    "/invoice-matches/{match_id}/post",
    response_model=InvoiceMatchDetail,
    dependencies=[Depends(require_permission(PROCUREMENT_INVOICE_MATCH_POST))],
)
async def post_invoice_match(
    match_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _PostIdem,
) -> InvoiceMatchDetail:
    """Post a MATCHED match (PLAN 6.4, D-042): creates + posts the AP vendor bill (Dr GR/IR + PPV /
    Cr AP) via the event bus, raises the PO billed_quantity, advances the PO toward CLOSED — all one
    transaction. A closed invoice period rolls the whole post back. IDEMPOTENT (D-013)."""
    holder: dict[str, InvoiceMatchDetail] = {}

    async def work() -> None:
        await service.post_invoice_match(session, current.tenant_id, match_id)
        detail = await match_detail(session, current.tenant_id, match_id)
        holder["read"] = await idem.capture(detail)

    await run_in_uow(session, work)
    return holder["read"]


@invoice_match_router.post(
    "/invoice-matches/{match_id}/override",
    response_model=InvoiceMatchDetail,
    dependencies=[Depends(require_permission(PROCUREMENT_INVOICE_MATCH_MANAGE))],
)
async def override_invoice_match(
    match_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> InvoiceMatchDetail:
    """Clear an EXCEPTION so the match may post (PLAN 6.4 — the invoice-release control). The
    authorized user accepts the price difference; the audited status change records it."""
    holder: dict[str, InvoiceMatchDetail] = {}

    async def work() -> None:
        await service.override_invoice_match(session, current.tenant_id, match_id)
        holder["read"] = await match_detail(session, current.tenant_id, match_id)

    await run_in_uow(session, work)
    return holder["read"]


@invoice_match_router.post(
    "/invoice-matches/{match_id}/cancel",
    response_model=InvoiceMatchDetail,
    dependencies=[Depends(require_permission(PROCUREMENT_INVOICE_MATCH_MANAGE))],
)
async def cancel_invoice_match(
    match_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> InvoiceMatchDetail:
    """Cancel a match before posting (PLAN 6.4). A POSTED match is terminal (corrected by a credit
    memo / reversal, Phase 7)."""
    holder: dict[str, InvoiceMatchDetail] = {}

    async def work() -> None:
        await service.cancel_invoice_match(session, current.tenant_id, match_id)
        holder["read"] = await match_detail(session, current.tenant_id, match_id)

    await run_in_uow(session, work)
    return holder["read"]


# --- Match tolerance config ---------------------------------------------------


@invoice_match_router.get(
    "/match-tolerances",
    response_model=MatchToleranceRead | None,
    dependencies=[Depends(require_permission(PROCUREMENT_INVOICE_MATCH_READ))],
)
async def get_match_tolerance(
    current: CurrentUserDep, session: SessionDep
) -> MatchToleranceRead | None:
    """The tenant's configured 3-way-match tolerances, or null when it runs on the strict defaults
    (PLAN 6.4)."""
    row = await service.get_match_tolerance(session, current.tenant_id)
    return MatchToleranceRead.model_validate(row) if row is not None else None


@invoice_match_router.put(
    "/match-tolerances",
    response_model=MatchToleranceRead,
    dependencies=[Depends(require_permission(PROCUREMENT_INVOICE_MATCH_MANAGE))],
)
async def upsert_match_tolerance(
    payload: MatchToleranceUpsert, current: CurrentUserDep, session: SessionDep
) -> MatchToleranceRead:
    """Set (or replace) the tenant's single 3-way-match tolerance row (PLAN 6.4)."""
    holder: dict[str, MatchToleranceRead] = {}

    async def work() -> None:
        row = await service.upsert_match_tolerance(session, current.tenant_id, payload)
        await session.refresh(row)
        holder["read"] = MatchToleranceRead.model_validate(row)

    await run_in_uow(session, work)
    return holder["read"]


# --- Reorder-point scan (PLAN 6.4 Part B) -------------------------------------


@invoice_match_router.post(
    "/reorder-scan",
    response_model=RequisitionDetail | None,
    dependencies=[Depends(require_permission(PROCUREMENT_REQUISITION_MANAGE))],
)
async def run_reorder_scan(
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _ScanIdem,
) -> RequisitionDetail | None:
    """Scan inventory for items at/below their reorder point and raise a DRAFT requisition proposing
    replenishment (PLAN 6.4, D-042). Skips items already on an open requisition line (idempotent
    dedup), so a second scan does not duplicate proposals. Returns the created requisition, or null
    (200) when nothing needs reordering. IDEMPOTENT (D-013)."""
    holder: dict[str, RequisitionDetail | None] = {}

    async def work() -> None:
        req = await service.run_reorder_scan(
            session, current.tenant_id, requested_by=current.user_id
        )
        if req is None:
            holder["read"] = await idem.capture(None)
            return
        lines = await service.get_requisition_lines(session, current.tenant_id, req.id)
        from app.modules.procurement.schemas import RequisitionLineRead

        header = RequisitionRead.model_validate(req)
        detail = RequisitionDetail(
            **header.model_dump(),
            lines=[RequisitionLineRead.model_validate(line) for line in lines],
        )
        holder["read"] = await idem.capture(detail, status_code=201)

    await run_in_uow(session, work)
    return holder["read"]
