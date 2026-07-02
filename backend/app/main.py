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
from app.core.bootstrap import mount_routers, register_event_handlers
from app.core.config import Settings, get_settings
from app.core.exceptions import AtlasError, translate_db_guard_error
from app.core.idempotency import REPLAYED_HEADER, IdempotencyReplay
from app.core.rbac import current_permissions
from app.core.schemas import ErrorBody, ErrorEnvelope
from app.core.tenancy import current_tenant_id

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

    # Router mounting + cross-module event-handler registration (D-011) live in core/bootstrap.py
    # (the two wiring blocks that grow with every module). mount_routers includes every module
    # router in the fixed import order; register_event_handlers subscribes the cross-module handlers
    # in that same deterministic order — importing each module runs its ``@on`` subscriptions.
    mount_routers(app)
    register_event_handlers()

    return app


app = create_app()
