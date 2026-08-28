"""Shared Pydantic v2 bases: API model config, D-014 error envelope, list envelope.

Auth request/response schemas (LoginRequest, TokenResponse, MeResponse) also live
here rather than in a module: auth is core platform (D-008), and there is no
modules/auth package — see core/security_router.py.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    """Base for all API schemas: ORM-attribute loading, str enums serialized as values."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class ErrorBody(ApiModel):
    code: str
    message: str
    # list for validation errors ([{field, message, type}]), dict for domain details.
    details: list[Any] | dict[str, Any] | None = None
    request_id: str | None = None


class ErrorEnvelope(ApiModel):
    error: ErrorBody


class Page[T](ApiModel):
    """List envelope per D-014 — no total counts. The keyset-cursor mechanics that mint
    ``next_cursor`` live in core/pagination.paginate; this is the wire shape it returns."""

    items: list[T]
    next_cursor: str | None = None
    limit: int


# --- Auth schemas (D-008) -----------------------------------------------------
# email is a plain str (not EmailStr) so no email-validator dependency is pulled in;
# the User model column is likewise a plain String.


class LoginRequest(ApiModel):
    tenant_slug: str
    email: str
    password: str


class TokenResponse(ApiModel):
    """Login/refresh body. The refresh token never appears here — it is set as an
    httpOnly cookie; only the access token is returned for SPA in-memory storage."""

    access_token: str
    token_type: str = "bearer"


class MeResponse(ApiModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    #: The organisation's display name. The SPA has no other read of it (a tenant read is an
    #: admin endpoint a server does not hold), and paper needs it: a printed check without the
    #: property's name on it is not a check (#211).
    tenant_name: str
    email: str
    full_name: str | None
    permissions: list[str]


# --- Document-flow schemas (D-012) --------------------------------------------
# The flow-chain read API serializes core/docflow's ChainNode/ChainEdge dataclasses.
# Kept here (not beside the router) to match the auth-schema precedent: core platform
# response models live in core/schemas.py, not a module.


class DocumentRead(ApiModel):
    """A registry entry as the API exposes it (D-012)."""

    id: uuid.UUID
    doc_type: str
    doc_id: uuid.UUID
    doc_number: str | None
    status: str | None


class DocChainNode(ApiModel):
    """One document node in a flow chain (mirrors core/docflow.ChainNode)."""

    document_id: uuid.UUID
    doc_type: str
    doc_id: uuid.UUID
    doc_number: str | None
    status: str | None


class DocChainEdge(ApiModel):
    """One predecessor -> successor edge in a flow chain (mirrors core/docflow.ChainEdge)."""

    predecessor_document_id: uuid.UUID
    successor_document_id: uuid.UUID
    link_type: str | None


class DocChainResponse(ApiModel):
    """The full bidirectional chain the DocFlowViewer renders: nodes + edges (D-012)."""

    nodes: list[DocChainNode]
    edges: list[DocChainEdge]


# --- Background-job schemas (PLAN 4P.5) ----------------------------------------
# Same precedent as the auth schemas: core platform response models live here, not in a
# module. ``status`` is the JobStatus string value (core/jobs.py owns the enum; a plain str
# here avoids importing the trailing-registered jobs module into this early-loading file).


class JobSubmitted(ApiModel):
    """The 202 body of an endpoint that backgrounds its work: poll /api/v1/jobs/{job_id}."""

    job_id: uuid.UUID
    status: str


class JobRead(ApiModel):
    """One background job as the polling endpoints expose it (status/result/error/timing)."""

    id: uuid.UUID
    job_type: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
    submitted_by_user_id: uuid.UUID | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


# Field-level read masking (D-009) lives in core/rbac.py with the rest of the RBAC
# engine; re-exported here so D-009's stated home (Masked in core/schemas.py) holds and
# module schemas import it alongside ApiModel from one surface.
from app.core.rbac import Masked  # noqa: E402 - re-export at end avoids an import cycle

__all__ = [
    "ApiModel",
    "DocChainEdge",
    "DocChainNode",
    "DocChainResponse",
    "DocumentRead",
    "ErrorBody",
    "ErrorEnvelope",
    "JobRead",
    "JobSubmitted",
    "LoginRequest",
    "Masked",
    "MeResponse",
    "Page",
    "TokenResponse",
]
