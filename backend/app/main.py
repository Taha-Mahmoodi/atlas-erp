"""App factory and app-level plumbing: request id, CORS, error envelope, health."""

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.audit import actor_user_id_ctx, request_id_ctx, request_ip_ctx
from app.core.config import Settings, get_settings
from app.core.docflow_router import router as docflow_router
from app.core.exceptions import AtlasError, translate_db_guard_error
from app.core.idempotency import REPLAYED_HEADER, IdempotencyReplay
from app.core.jobs_router import router as jobs_router
from app.core.rbac import current_permissions
from app.core.schemas import ErrorBody, ErrorEnvelope
from app.core.security_router import router as security_router
from app.core.tenancy import current_tenant_id
from app.modules.finance.router import router as finance_router
from app.modules.inventory.router import router as inventory_router
from app.modules.maintenance.router import router as maintenance_router
from app.modules.manufacturing.router import router as manufacturing_router
from app.modules.procurement.router import router as procurement_router
from app.modules.quality.router import router as quality_router
from app.modules.sales.router import router as sales_router

logger = logging.getLogger("atlas")

API_PREFIX = "/api/v1"

# request_id lives in the audit module (core/audit.py owns the request-context ContextVars);
# re-exported under the historical name so existing callers/tests keep one import.
request_id_var = request_id_ctx


def _client_ip(scope: Scope, trust_proxy: bool) -> str | None:
    """Audited client IP (D-010). Default: the raw transport peer (scope['client']). Only
    when ATLAS_TRUST_PROXY is on do we honor the LEFT-MOST X-Forwarded-For hop — otherwise a
    client could spoof its own audited IP just by sending the header."""
    if trust_proxy:
        for raw_name, raw_value in scope.get("headers", ()):
            if raw_name == b"x-forwarded-for":
                first_hop = raw_value.decode("latin-1").split(",")[0].strip()
                if first_hop:
                    return first_hop
    client = scope.get("client")
    return client[0] if client else None


class RequestIdMiddleware:
    """Pure-ASGI: one uuid4-hex request id per request, exposed via ContextVar,
    request.state and the X-Request-ID response header.

    It ALSO owns the D-007 tenancy-ContextVar reset, the D-009 current_permissions reset,
    and the D-010 audit-context (request_id, request_ip, actor_user_id) lifecycle:
    get_current_user sets the tenant/permissions/actor vars directly (no context manager),
    so this middleware captures reset tokens in a finally block — otherwise request A's
    context would leak into request B reusing the same worker/task. request_id and
    request_ip are seeded here at the edge; actor_user_id starts None (system/unauth) and is
    filled by get_current_user once the principal is known. All are reset on the way out, so
    the worker always restarts at the defaults."""

    def __init__(self, app: ASGIApp, trust_proxy: bool) -> None:
        self.app = app
        self.trust_proxy = trust_proxy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_var.set(request_id)
        ip_token = request_ip_ctx.set(_client_ip(scope, self.trust_proxy))
        actor_token = actor_user_id_ctx.set(None)
        tenant_token = current_tenant_id.set(None)
        permissions_token = current_permissions.set(frozenset())

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            current_permissions.reset(permissions_token)
            current_tenant_id.reset(tenant_token)
            actor_user_id_ctx.reset(actor_token)
            request_ip_ctx.reset(ip_token)
            request_id_var.reset(token)


def _request_id(request: Request) -> str | None:
    # The ContextVar is already reset when the catch-all handler runs (Starlette's
    # ServerErrorMiddleware sits outside RequestIdMiddleware), hence the state fallback.
    return request_id_var.get() or getattr(request.state, "request_id", None)


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: list[Any] | dict[str, Any] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    envelope = ErrorEnvelope(
        error=ErrorBody(code=code, message=message, details=details, request_id=request_id)
    )
    # Set the header here too: 500 responses bypass RequestIdMiddleware's send wrapper.
    headers = {"X-Request-ID": request_id} if request_id else None
    return JSONResponse(status_code=status_code, content=envelope.model_dump(), headers=headers)


async def _handle_atlas_error(request: Request, exc: AtlasError) -> JSONResponse:
    return _error_response(request, exc.status_code, exc.code, exc.message, exc.details)


async def _handle_idempotency_replay(
    request: Request, exc: IdempotencyReplay
) -> JSONResponse:
    # D-013 replay short-circuit: a completed key with a matching body hash never runs the
    # handler. reserve() raised this carrying the stored status + body; we re-emit them verbatim
    # with the Idempotency-Replayed marker so the side effect cannot run twice. Registered BEFORE
    # the generic AtlasError handler (more specific subclass) so it wins dispatch.
    request_id = _request_id(request)
    headers = {REPLAYED_HEADER: "true"}
    if request_id:
        headers["X-Request-ID"] = request_id
    return JSONResponse(
        status_code=exc.status_code, content=exc.response_body, headers=headers
    )


async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "common.not_found" if exc.status_code == 404 else "common.http_error"
    return _error_response(request, exc.status_code, code, str(exc.detail))


async def _handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = [
        {
            "field": ".".join(str(part) for part in err.get("loc", ())),
            "message": err.get("msg", ""),
            "type": err.get("type", ""),
        }
        for err in exc.errors()
    ]
    return _error_response(
        request, 422, "common.validation_error", "Request validation failed", details
    )


async def _handle_db_guard_error(request: Request, exc: DBAPIError) -> JSONResponse:
    # D-014: a DB trigger that raised an ATLAS_* token surfaces through the same envelope
    # as service-level checks (e.g. ATLAS_AUDIT_APPEND_ONLY -> 409 audit.append_only). A
    # DBAPIError WITHOUT a known token is a genuine integrity/operational fault — log it and
    # return the opaque 500 like any unexpected error, never leaking raw DB text.
    translated = translate_db_guard_error(exc)
    if translated is not None:
        return _error_response(
            request, translated.status_code, translated.code, translated.message
        )
    logger.exception("Database error (request_id=%s)", _request_id(request), exc_info=exc)
    return _error_response(request, 500, "common.internal_error", "Internal server error")


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # Log with request id; never leak the traceback into the response body.
    logger.exception("Unhandled error (request_id=%s)", _request_id(request), exc_info=exc)
    return _error_response(request, 500, "common.internal_error", "Internal server error")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level.upper())

    app = FastAPI(
        title="Atlas ERP",
        version="0.1.0",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Response compression (PERFORMANCE §3): bodies >= 500 bytes are gzipped when the client
    # sends Accept-Encoding: gzip; tiny responses pass through uncompressed. Added between
    # CORS and RequestIdMiddleware, so the request id header is stamped outside compression.
    app.add_middleware(GZipMiddleware, minimum_size=500)
    # Added last == outermost user middleware: the request id exists for everything
    # below it, including CORS rejections.
    app.add_middleware(RequestIdMiddleware, trust_proxy=settings.trust_proxy)

    # IdempotencyReplay is an AtlasError subclass; register it FIRST so Starlette dispatches a
    # replay to its verbatim-response handler before the generic envelope handler (D-013).
    app.add_exception_handler(IdempotencyReplay, _handle_idempotency_replay)
    app.add_exception_handler(AtlasError, _handle_atlas_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    # DBAPIError is more specific than Exception, so Starlette dispatches DB-guard tokens
    # (D-014) here before falling through to the catch-all 500 below.
    app.add_exception_handler(DBAPIError, _handle_db_guard_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)

    @app.get(f"{API_PREFIX}/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.env}

    # Core platform auth endpoints (D-008): login/refresh/logout/me at /api/v1/auth.
    app.include_router(security_router)
    # Core platform document-flow read endpoint (D-012): GET /api/v1/documents/{id}/chain.
    app.include_router(docflow_router)
    # Core platform background-job polling (PLAN 4P.5/D-032): GET /api/v1/jobs[/{id}].
    app.include_router(jobs_router)
    # Finance module (PLAN 4): chart of accounts + fiscal years/periods at /api/v1/finance.
    # First business module mounted; the fixed import order here is also the D-011 handler
    # registration order (finance, then inventory, ...) once modules publish/subscribe events.
    app.include_router(finance_router)
    # Inventory module (PLAN 5): item masters at /api/v1/inventory. Mounted after finance, the
    # D-011 handler-registration order; inventory reads finance/queries downward (STRUCTURE §5).
    app.include_router(inventory_router)
    # Procurement module (PLAN 6): vendor master at /api/v1/procurement. Mounted after inventory,
    # the D-011 handler-registration order; procurement OWNS the vendor entity and reads
    # finance/queries + inventory/queries downward (STRUCTURE §5 / D-029).
    app.include_router(procurement_router)
    # Sales module (PLAN 7): customer master + condition-style pricing at /api/v1/sales. Mounted
    # after procurement, the D-011 handler-registration order; sales OWNS the customer entity and
    # reads finance/queries + inventory/queries downward (STRUCTURE §5 / D-029). 7.1 publishes no
    # cross-module events (masters + pricing drive no effects; orders in 7.2 will).
    app.include_router(sales_router)
    # Manufacturing module (PLAN 8): PP master data (work centres, multi-level versioned BOMs,
    # routings) at /api/v1/manufacturing. Mounted after sales, the D-011 handler-registration
    # order; manufacturing reads finance/queries + inventory/queries downward (STRUCTURE §5 /
    # D-029). 8.1 publishes no cross-module events (masters drive no effects; production orders in
    # 8.2 will).
    app.include_router(manufacturing_router)
    # Quality module (PLAN 9): inspection lots at /api/v1/quality. Mounted after manufacturing, the
    # D-011 handler-registration order; quality SUBSCRIBES to procurement's GoodsReceiptPosted to
    # create inspection lots and reads inventory/queries downward (STRUCTURE §5 / D-029 / D-050). A
    # reject disposition publishes InspectionDispositioned → inventory moves the rejected stock.
    app.include_router(quality_router)
    # Maintenance module (PLAN 9.2): equipment + corrective/preventive orders + interval plans at
    # /api/v1/maintenance. Mounted after quality, the D-011 module import order; maintenance reads
    # finance/queries downward for an equipment's optional cost centre (STRUCTURE §5 / D-029 /
    # D-051). It publishes/subscribes to NO cross-module event in v1 — a completed order records its
    # cost on the order row (record-only, no GL posting, D-051).
    app.include_router(maintenance_router)

    # Cross-module event handlers (D-011): registered here, at the app factory, so registration
    # order
    # is the deterministic module import order. Importing the module runs its ``@on`` subscriptions.
    # finance/handlers posts the COGS/inventory journal for an inventory ``stock.valued`` event in
    # the
    # SAME transaction as the move (PLAN 5.3, D-020) — the first real cross-module handler.
    register_event_handlers()

    return app


def register_event_handlers() -> None:
    """Register the cross-module domain-event handlers (D-011), in the deterministic module order.

    Called from ``create_app`` (the registration seam) and available to seed/CLI flows that build
    the
    bus without the HTTP app. IDEMPOTENT and re-runnable: each handler is (re)subscribed only if not
    already present for its key, so building several apps in one process — or re-registering after
    the
    test harness's ``clear_subscriptions`` reset (D-025) — yields exactly one subscription per
    handler, never a duplicate that would double-post."""
    from app.core.events import handlers_for, subscribe
    from app.modules.finance.handlers import (
        create_bill_for_match,
        create_credit_note_for_return,
        create_invoice_for_billing,
        post_production_variance,
        post_stock_valuation_journal,
    )
    from app.modules.inventory.events import StockValued
    from app.modules.inventory.handlers import (
        disposition_rejected_stock,
        issue_delivery_moves,
        issue_production_components,
        receive_finished_order_move,
        receive_goods_receipt_moves,
        receive_return_moves,
    )
    from app.modules.manufacturing.events import (
        ComponentsIssued,
        OrderFinished,
        PlannedBuyConverted,
    )
    from app.modules.procurement.events import GoodsReceiptPosted, InvoiceMatched
    from app.modules.procurement.handlers import create_requisition_for_planned_buy
    from app.modules.quality.events import InspectionDispositioned
    from app.modules.quality.handlers import create_inspection_lots_for_receipt
    from app.modules.sales.events import (
        BillingInvoiced,
        DeliveryShipped,
        ReturnCredited,
        ReturnReceived,
    )

    if post_stock_valuation_journal not in handlers_for(StockValued.key):
        subscribe(StockValued.key, post_stock_valuation_journal)
    # Procurement goods-receipt → inventory stock-move bridge (PLAN 6.3, D-041): inventory's
    # handler creates the RECEIPT moves (Cr GR-IR) when a GR posts, which in turn publish
    # StockValued for the finance handler above — a two-hop same-transaction chain
    # (procurement → inventory → finance).
    if receive_goods_receipt_moves not in handlers_for(GoodsReceiptPosted.key):
        subscribe(GoodsReceiptPosted.key, receive_goods_receipt_moves)
    # Sales delivery → inventory stock-move bridge (PLAN 7.3, D-045): the OUTBOUND twin of the GR
    # bridge — inventory's handler creates the ISSUE moves (Dr COGS / Cr Inventory, COGS the default
    # issue offset — no override) when a delivery posts, which in turn publish StockValued for the
    # finance handler above — the same two-hop same-transaction chain (sales → inventory → finance).
    if issue_delivery_moves not in handlers_for(DeliveryShipped.key):
        subscribe(DeliveryShipped.key, issue_delivery_moves)
    # Procurement invoice-match → finance AP-bill bridge (PLAN 6.4, D-042): finance's handler
    # creates + posts the matched vendor bill (Dr GR/IR + PPV / Cr AP) when a match posts, clearing
    # the GR/IR account the goods receipt credited — closing the procure-to-pay loop. Procurement
    # publishes; finance handles its own bill posting (STRUCTURE §5).
    if create_bill_for_match not in handlers_for(InvoiceMatched.key):
        subscribe(InvoiceMatched.key, create_bill_for_match)
    # Sales billing → finance AR-invoice bridge (PLAN 7.4, D-046): the MIRROR of the invoice-match →
    # AP-bill bridge, sign-flipped — finance's handler creates + posts the AR customer invoice (Dr
    # AR
    # control / Cr revenue + tax) when a billing posts. Sales publishes; finance handles its own
    # invoice posting (STRUCTURE §5).
    if create_invoice_for_billing not in handlers_for(BillingInvoiced.key):
        subscribe(BillingInvoiced.key, create_invoice_for_billing)
    # Sales return → inventory RECEIPT bridge (PLAN 7.4, D-046): inventory's handler receives the
    # goods back (Dr Inventory / Cr COGS via the COGS-offset override — reversing the delivery's
    # issue) when a return posts, which publishes StockValued for the finance COGS handler above.
    if receive_return_moves not in handlers_for(ReturnReceived.key):
        subscribe(ReturnReceived.key, receive_return_moves)
    # Sales return → finance AR-credit-note bridge (PLAN 7.4, D-046): finance's handler creates +
    # posts the AR credit note (Dr revenue / Cr AR + reverse tax — reversing the billing) when a
    # return posts. The second leg of an atomic return post (the first is the stock receipt above).
    if create_credit_note_for_return not in handlers_for(ReturnCredited.key):
        subscribe(ReturnCredited.key, create_credit_note_for_return)
    # Manufacturing production-order → inventory stock-move bridges (PLAN 8.2, D-048), the
    # manufacturing↔inventory↔finance seam. A component ISSUE posts Dr WIP / Cr Inventory (the
    # valuation-offset OVERRIDE to the WIP account — the 6.3 GR/IR-override pattern applied to an
    # ISSUE) and a finished RECEIPT posts Dr Inventory / Cr WIP, both via inventory's handlers
    # creating the moves which in turn publish StockValued for the finance handler above — the same
    # two-hop same-transaction chain (manufacturing → inventory → finance). WIP nets to zero per
    # fully-issued + finished order; the variance flush is posted by manufacturing's finish flow.
    if issue_production_components not in handlers_for(ComponentsIssued.key):
        subscribe(ComponentsIssued.key, issue_production_components)
    # OrderFinished has TWO same-transaction subscribers: inventory's handler creates the finished
    # RECEIPT move (Dr Inventory / Cr WIP) and finance's handler posts the residual WIP variance (so
    # WIP nets to zero). Both drain in the finish's uow; either failure rolls the whole finish back.
    if receive_finished_order_move not in handlers_for(OrderFinished.key):
        subscribe(OrderFinished.key, receive_finished_order_move)
    if post_production_variance not in handlers_for(OrderFinished.key):
        subscribe(OrderFinished.key, post_production_variance)
    # Manufacturing planned-BUY → procurement DRAFT-requisition bridge (PLAN 8.3, D-049): a planned
    # BUY order's conversion publishes PlannedBuyConverted and procurement's handler creates the
    # requisition in the SAME transaction, linking the MRP run document → 'planned_to' → requisition
    # (the §5-clean planned-BUY → requisition mechanism — manufacturing never imports procurement
    # service, the billing → AR-invoice precedent).
    if create_requisition_for_planned_buy not in handlers_for(PlannedBuyConverted.key):
        subscribe(PlannedBuyConverted.key, create_requisition_for_planned_buy)
    # GoodsReceiptPosted has TWO same-transaction subscribers (PLAN 9.1, D-050): inventory's
    # receive_goods_receipt_moves (registered above) creates the RECEIPT moves, then quality's
    # create_inspection_lots_for_receipt creates an OPEN inspection lot per requires_inspection
    # line.
    # Quality is subscribed AFTER inventory (registration order = dispatch order, D-011) so the
    # lot/serial master instance the receipt creates already exists when quality resolves the GR
    # line's code to a traceability id.
    if create_inspection_lots_for_receipt not in handlers_for(GoodsReceiptPosted.key):
        subscribe(GoodsReceiptPosted.key, create_inspection_lots_for_receipt)
    # Quality reject-disposition → inventory stock-move bridge (PLAN 9.1, D-050): a REJECT usage
    # decision publishes InspectionDispositioned and inventory's handler moves the rejected stock
    # (SCRAP = an ADJUSTMENT-out write-off → Dr inventory-adjustment / Cr Inventory; BLOCK = a
    # value-neutral TRANSFER to the blocked bin) in the SAME transaction. Quality publishes;
    # inventory handles its own move (STRUCTURE §5). An ACCEPT publishes nothing — accepted stock is
    # already received and usable.
    if disposition_rejected_stock not in handlers_for(InspectionDispositioned.key):
        subscribe(InspectionDispositioned.key, disposition_rejected_stock)


app = create_app()
