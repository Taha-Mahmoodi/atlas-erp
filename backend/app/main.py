"""App factory and app-level plumbing: request id, CORS, error envelope, health."""

import logging
import uuid
from contextvars import ContextVar
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings, get_settings
from app.core.exceptions import AtlasError
from app.core.rbac import current_permissions
from app.core.schemas import ErrorBody, ErrorEnvelope
from app.core.security_router import router as security_router
from app.core.tenancy import current_tenant_id

logger = logging.getLogger("atlas")

API_PREFIX = "/api/v1"

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class RequestIdMiddleware:
    """Pure-ASGI: one uuid4-hex request id per request, exposed via ContextVar,
    request.state and the X-Request-ID response header.

    It ALSO owns the D-007 tenancy-ContextVar reset AND the D-009 current_permissions
    reset: get_current_user sets both directly (no context manager), so this middleware
    captures reset tokens in a finally block — otherwise request A's tenant/permissions
    would leak into request B reusing the same worker/task. The tokens are captured here,
    the vars are set deeper in the stack, and reset on the way out, so the worker always
    restarts at the defaults (None / empty frozenset)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_var.set(request_id)
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
    # Added last == outermost user middleware: the request id exists for everything
    # below it, including CORS rejections.
    app.add_middleware(RequestIdMiddleware)

    app.add_exception_handler(AtlasError, _handle_atlas_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)

    @app.get(f"{API_PREFIX}/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.env}

    # Core platform auth endpoints (D-008): login/refresh/logout/me at /api/v1/auth.
    app.include_router(security_router)

    return app


app = create_app()
