"""Accounts Receivable HTTP layer (PLAN 4.6), included into the finance router.

The AP ``ap_router.py`` mirror. Split out of router.py (at the STRUCTURE §3 400-line cap) the same
way fx_router/tax_router/ap_router are: mounted via ``router.include_router(ar_router)`` so the
module stays ONE surface at ``/api/v1/finance`` — no second mount in main.py. Reads are guarded by
``finance.ar.read``, invoice create/post by ``finance.ar.manage``, receipts + dunning by
``finance.ar.collect`` (D-009). Writes commit through ``run_in_uow`` (D-011) so audit + events ride
the transaction; the financial-document endpoints (post invoice, create receipt) and the dunning run
are IDEMPOTENT (D-013). ``partner_id`` is opaque throughout (D-029).
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
    FINANCE_AR_COLLECT,
    FINANCE_AR_MANAGE,
    FINANCE_AR_READ,
)
from app.modules.finance.receivables_schemas import (
    ArAgingReportRead,
    CustomerInvoiceCreate,
    CustomerInvoiceDetail,
    CustomerInvoiceLineRead,
    CustomerInvoiceRead,
    CustomerReceiptCreate,
    CustomerReceiptDetail,
    CustomerReceiptRead,
    DunningRunRequest,
    DunningRunResult,
    ReceiptAllocationRead,
)

ar_router = APIRouter(tags=["finance-ar"])

CursorParamsDep = Depends(cursor_params)
_PostInvoiceIdempotentDep = Depends(Idempotent("finance.ar.invoice.post"))
_ReceiptIdempotentDep = Depends(Idempotent("finance.ar.receipt"))
_DunningIdempotentDep = Depends(Idempotent("finance.ar.dunning_run"))


async def _invoice_detail(
    session: SessionDep, tenant_id: uuid.UUID, invoice_id: uuid.UUID
) -> CustomerInvoiceDetail:
    """Load an invoice + its lines into the detail schema. ``refresh`` materializes server defaults
    in the async context before the sync ``model_validate`` (else an expired attribute triggers an
    async lazy-load in sync serialization — MissingGreenlet)."""
    invoice = await service.get_customer_invoice(session, tenant_id, invoice_id)
    await session.refresh(invoice)
    lines = await service.get_customer_invoice_lines(session, tenant_id, invoice_id)
    header = CustomerInvoiceRead.model_validate(invoice)
    return CustomerInvoiceDetail(
        **header.model_dump(),
        lines=[CustomerInvoiceLineRead.model_validate(line) for line in lines],
    )


async def _receipt_detail(
    session: SessionDep, tenant_id: uuid.UUID, receipt_id: uuid.UUID
) -> CustomerReceiptDetail:
    receipt = await service.get_customer_receipt(session, tenant_id, receipt_id)
    await session.refresh(receipt)
    allocations = await service.get_receipt_allocations(session, tenant_id, receipt_id)
    header = CustomerReceiptRead.model_validate(receipt)
    return CustomerReceiptDetail(
        **header.model_dump(),
        allocations=[ReceiptAllocationRead.model_validate(a) for a in allocations],
    )


# --- Customer invoices --------------------------------------------------------


@ar_router.post(
    "/customer-invoices",
    response_model=CustomerInvoiceRead,
    status_code=201,
    dependencies=[Depends(require_permission(FINANCE_AR_MANAGE))],
)
async def create_customer_invoice(
    payload: CustomerInvoiceCreate, current: CurrentUserDep, session: SessionDep
) -> CustomerInvoiceRead:
    """Create a DRAFT customer invoice (no number/journal). Use the /post action to post it."""
    holder: dict[str, CustomerInvoiceRead] = {}

    async def work() -> None:
        invoice = await service.create_customer_invoice(session, current.tenant_id, payload)
        await session.refresh(invoice)
        holder["read"] = CustomerInvoiceRead.model_validate(invoice)

    await run_in_uow(session, work)
    return holder["read"]


@ar_router.post(
    "/customer-invoices/{invoice_id}/post",
    response_model=CustomerInvoiceDetail,
    dependencies=[Depends(require_permission(FINANCE_AR_MANAGE))],
)
async def post_customer_invoice(
    invoice_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _PostInvoiceIdempotentDep,
) -> CustomerInvoiceDetail:
    """Post a draft customer invoice to the journal (PLAN 4.6). IDEMPOTENT (D-013): capture() lands
    in the posting uow, so the document + replay record commit atomically."""
    holder: dict[str, CustomerInvoiceDetail] = {}

    async def work() -> None:
        await service.post_customer_invoice(session, current.tenant_id, invoice_id)
        detail = await _invoice_detail(session, current.tenant_id, invoice_id)
        holder["read"] = await idem.capture(detail)

    await run_in_uow(session, work)
    return holder["read"]


@ar_router.get(
    "/customer-invoices",
    response_model=Page[CustomerInvoiceRead],
    dependencies=[Depends(require_permission(FINANCE_AR_READ))],
)
async def list_customer_invoices(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    status: str | None = None,
    partner_id: uuid.UUID | None = None,
) -> Page[CustomerInvoiceRead]:
    page = await service.list_customer_invoices(
        session,
        current.tenant_id,
        cursor=params.cursor,
        limit=params.limit,
        status=status,
        partner_id=partner_id,
    )
    return Page(
        items=[CustomerInvoiceRead.model_validate(item) for item in page.items],
        next_cursor=page.next_cursor,
        limit=page.limit,
    )


@ar_router.get(
    "/customer-invoices/{invoice_id}",
    response_model=CustomerInvoiceDetail,
    dependencies=[Depends(require_permission(FINANCE_AR_READ))],
)
async def get_customer_invoice(
    invoice_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> CustomerInvoiceDetail:
    return await _invoice_detail(session, current.tenant_id, invoice_id)


# --- Customer receipts --------------------------------------------------------


@ar_router.post(
    "/customer-receipts",
    response_model=CustomerReceiptDetail,
    status_code=201,
    dependencies=[Depends(require_permission(FINANCE_AR_COLLECT))],
)
async def create_customer_receipt(
    payload: CustomerReceiptCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _ReceiptIdempotentDep,
) -> CustomerReceiptDetail:
    """Create + post a customer receipt clearing open invoices (PLAN 4.6). IDEMPOTENT (D-013): it
    posts a journal entry + clears open items, so a retried request must not double-receive."""
    holder: dict[str, CustomerReceiptDetail] = {}

    async def work() -> None:
        receipt = await service.create_and_post_receipt(session, current.tenant_id, payload)
        detail = await _receipt_detail(session, current.tenant_id, receipt.id)
        holder["read"] = await idem.capture(detail, status_code=201)

    await run_in_uow(session, work)
    return holder["read"]


@ar_router.get(
    "/customer-receipts",
    response_model=Page[CustomerReceiptRead],
    dependencies=[Depends(require_permission(FINANCE_AR_READ))],
)
async def list_customer_receipts(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    partner_id: uuid.UUID | None = None,
) -> Page[CustomerReceiptRead]:
    page = await service.list_customer_receipts(
        session,
        current.tenant_id,
        cursor=params.cursor,
        limit=params.limit,
        partner_id=partner_id,
    )
    return Page(
        items=[CustomerReceiptRead.model_validate(item) for item in page.items],
        next_cursor=page.next_cursor,
        limit=page.limit,
    )


# --- Dunning ------------------------------------------------------------------


@ar_router.post(
    "/dunning-runs",
    response_model=DunningRunResult,
    status_code=201,
    dependencies=[Depends(require_permission(FINANCE_AR_COLLECT))],
)
async def run_dunning(
    payload: DunningRunRequest,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _DunningIdempotentDep,
) -> DunningRunResult:
    """Run a dunning pass (PLAN 4.6): advance the reminder level on overdue open invoices and return
    the notice list. Posts no journal. IDEMPOTENT (D-013) and idempotent-ish per day (a re-run the
    same ``as_of`` advances nothing already at its earned level)."""
    holder: dict[str, DunningRunResult] = {}

    async def work() -> None:
        run = await service.run_dunning(
            session, current.tenant_id, payload.as_of, payload.partner_id
        )
        result = DunningRunResult.model_validate(run)
        holder["read"] = await idem.capture(result, status_code=201)

    await run_in_uow(session, work)
    return holder["read"]


# --- AR aging -----------------------------------------------------------------


@ar_router.get(
    "/ar-aging",
    response_model=ArAgingReportRead,
    dependencies=[Depends(require_permission(FINANCE_AR_READ))],
)
async def ar_aging(
    current: CurrentUserDep,
    session: SessionDep,
    as_of: date,
    partner_id: uuid.UUID | None = None,
) -> ArAgingReportRead:
    """AR aging as of ``as_of`` (PLAN 4.6): per-partner buckets + totals over open invoices."""
    report = await service.customer_aging(session, current.tenant_id, as_of, partner_id)
    return ArAgingReportRead.model_validate(report)
