"""Accounts Payable HTTP layer (PLAN 4.5), included into the finance router.

Split out of router.py (at the STRUCTURE §3 400-line cap) the same way fx_router/tax_router are:
mounted via ``router.include_router(ap_router)`` so the module stays ONE surface at
``/api/v1/finance`` — no second mount in main.py. Reads are guarded by ``finance.ap.read``,
bill create/post by ``finance.ap.manage``, payments + payment runs by ``finance.ap.pay`` (D-009).
Writes commit through ``run_in_uow`` (D-011) so audit + events ride the transaction; the
financial-document endpoints (post bill, create payment, payment run) are IDEMPOTENT (D-013).
``partner_id`` is opaque throughout (D-029).
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.pagination import CursorParams, cursor_params
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.finance import service
from app.modules.finance.constants import (
    FINANCE_AP_MANAGE,
    FINANCE_AP_PAY,
    FINANCE_AP_READ,
)
from app.modules.finance.payables_schemas import (
    AgingReportRead,
    PaymentAllocationRead,
    PaymentRunRequest,
    PaymentRunResult,
    VendorBillCreate,
    VendorBillDetail,
    VendorBillLineRead,
    VendorBillRead,
    VendorPaymentCreate,
    VendorPaymentDetail,
    VendorPaymentRead,
)

ap_router = APIRouter(tags=["finance-ap"])

CursorParamsDep = Depends(cursor_params)
_PostBillIdempotentDep = Depends(Idempotent("finance.ap.bill.post"))
_PayIdempotentDep = Depends(Idempotent("finance.ap.payment"))
_RunIdempotentDep = Depends(Idempotent("finance.ap.payment_run"))


async def _bill_detail(
    session: SessionDep, tenant_id: uuid.UUID, bill_id: uuid.UUID
) -> VendorBillDetail:
    """Load a bill + its lines into the detail schema. ``refresh`` materializes server defaults in
    the async context before the sync ``model_validate`` (else an expired attribute triggers an
    async lazy-load in sync serialization — MissingGreenlet)."""
    bill = await service.get_vendor_bill(session, tenant_id, bill_id)
    await session.refresh(bill)
    lines = await service.get_vendor_bill_lines(session, tenant_id, bill_id)
    header = VendorBillRead.model_validate(bill)
    return VendorBillDetail(
        **header.model_dump(),
        lines=[VendorBillLineRead.model_validate(line) for line in lines],
    )


async def _payment_detail(
    session: SessionDep, tenant_id: uuid.UUID, payment_id: uuid.UUID
) -> VendorPaymentDetail:
    payment = await service.get_vendor_payment(session, tenant_id, payment_id)
    await session.refresh(payment)
    allocations = await service.get_payment_allocations(session, tenant_id, payment_id)
    header = VendorPaymentRead.model_validate(payment)
    return VendorPaymentDetail(
        **header.model_dump(),
        allocations=[PaymentAllocationRead.model_validate(a) for a in allocations],
    )


# --- Vendor bills -------------------------------------------------------------


@ap_router.post(
    "/vendor-bills",
    response_model=VendorBillRead,
    status_code=201,
    dependencies=[Depends(require_permission(FINANCE_AP_MANAGE))],
)
async def create_vendor_bill(
    payload: VendorBillCreate, current: CurrentUserDep, session: SessionDep
) -> VendorBillRead:
    """Create a DRAFT vendor bill (no number/journal). Use the /post action to post it."""
    holder: dict[str, VendorBillRead] = {}

    async def work() -> None:
        bill = await service.create_vendor_bill(session, current.tenant_id, payload)
        await session.refresh(bill)
        holder["read"] = VendorBillRead.model_validate(bill)

    await run_in_uow(session, work)
    return holder["read"]


@ap_router.post(
    "/vendor-bills/{bill_id}/post",
    response_model=VendorBillDetail,
    dependencies=[Depends(require_permission(FINANCE_AP_MANAGE))],
)
async def post_vendor_bill(
    bill_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _PostBillIdempotentDep,
) -> VendorBillDetail:
    """Post a draft vendor bill to the journal (PLAN 4.5). IDEMPOTENT (D-013): capture() lands in
    the posting uow, so the document + replay record commit atomically."""
    holder: dict[str, VendorBillDetail] = {}

    async def work() -> None:
        await service.post_vendor_bill(session, current.tenant_id, bill_id)
        detail = await _bill_detail(session, current.tenant_id, bill_id)
        holder["read"] = await idem.capture(detail)

    await run_in_uow(session, work)
    return holder["read"]


@ap_router.get(
    "/vendor-bills",
    response_model=Page[VendorBillRead],
    dependencies=[Depends(require_permission(FINANCE_AP_READ))],
)
async def list_vendor_bills(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    status: str | None = None,
    partner_id: uuid.UUID | None = None,
) -> Page[VendorBillRead]:
    page = await service.list_vendor_bills(
        session,
        current.tenant_id,
        cursor=params.cursor,
        limit=params.limit,
        status=status,
        partner_id=partner_id,
    )
    return Page(
        items=[VendorBillRead.model_validate(item) for item in page.items],
        next_cursor=page.next_cursor,
        limit=page.limit,
    )


@ap_router.get(
    "/vendor-bills/{bill_id}",
    response_model=VendorBillDetail,
    dependencies=[Depends(require_permission(FINANCE_AP_READ))],
)
async def get_vendor_bill(
    bill_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> VendorBillDetail:
    return await _bill_detail(session, current.tenant_id, bill_id)


# --- Vendor payments ----------------------------------------------------------


@ap_router.post(
    "/vendor-payments",
    response_model=VendorPaymentDetail,
    status_code=201,
    dependencies=[Depends(require_permission(FINANCE_AP_PAY))],
)
async def create_vendor_payment(
    payload: VendorPaymentCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _PayIdempotentDep,
) -> VendorPaymentDetail:
    """Create + post a vendor payment clearing open bills (PLAN 4.5). IDEMPOTENT (D-013): it posts a
    journal entry + clears open items, so a retried request must not double-pay."""
    holder: dict[str, VendorPaymentDetail] = {}

    async def work() -> None:
        payment = await service.create_and_post_payment(session, current.tenant_id, payload)
        detail = await _payment_detail(session, current.tenant_id, payment.id)
        holder["read"] = await idem.capture(detail, status_code=201)

    await run_in_uow(session, work)
    return holder["read"]


@ap_router.post(
    "/payment-runs",
    response_model=PaymentRunResult,
    status_code=201,
    dependencies=[Depends(require_permission(FINANCE_AP_PAY))],
)
async def run_payment_batch(
    payload: PaymentRunRequest,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _RunIdempotentDep,
) -> PaymentRunResult:
    """Run a payment batch (PLAN 4.5): pay every partner's due open bills in full. IDEMPOTENT
    (D-013): it posts one payment per partner, so a retry must not double-run. Returns the payments
    created, wrapped so the replay body serializes like every other captured response."""
    holder: dict[str, PaymentRunResult] = {}

    async def work() -> None:
        payments = await service.run_payment_batch(
            session,
            current.tenant_id,
            up_to_due_date=payload.up_to_due_date,
            bank_account_id=payload.bank_account_id,
            partner_id=payload.partner_id,
            payment_date=payload.payment_date,
        )
        for payment in payments:
            await session.refresh(payment)
        result = PaymentRunResult(
            payments=[VendorPaymentRead.model_validate(p) for p in payments]
        )
        holder["read"] = await idem.capture(result, status_code=201)

    await run_in_uow(session, work)
    return holder["read"]


@ap_router.get(
    "/vendor-payments",
    response_model=Page[VendorPaymentRead],
    dependencies=[Depends(require_permission(FINANCE_AP_READ))],
)
async def list_vendor_payments(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    partner_id: uuid.UUID | None = None,
) -> Page[VendorPaymentRead]:
    page = await service.list_vendor_payments(
        session,
        current.tenant_id,
        cursor=params.cursor,
        limit=params.limit,
        partner_id=partner_id,
    )
    return Page(
        items=[VendorPaymentRead.model_validate(item) for item in page.items],
        next_cursor=page.next_cursor,
        limit=page.limit,
    )


# --- AP aging -----------------------------------------------------------------


@ap_router.get(
    "/ap-aging",
    response_model=AgingReportRead,
    dependencies=[Depends(require_permission(FINANCE_AP_READ))],
)
async def ap_aging(
    current: CurrentUserDep,
    session: SessionDep,
    as_of: date,
    partner_id: uuid.UUID | None = None,
) -> AgingReportRead:
    """AP aging as of ``as_of`` (PLAN 4.5): per-partner buckets + totals over open bills."""
    report = await service.vendor_aging(session, current.tenant_id, as_of, partner_id)
    return AgingReportRead.model_validate(report)
