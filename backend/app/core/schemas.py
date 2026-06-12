"""Shared Pydantic v2 bases: API model config, D-014 error envelope, list envelope.

Auth request/response schemas (LoginRequest, TokenResponse, MeResponse) also live
here rather than in a module: auth is core platform (D-008), and there is no
modules/auth package — see core/security_router.py.
"""

import uuid
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
    """List envelope per D-014 — no total counts. Keyset-cursor mechanics arrive
    with the paginate helper in a later task; this is the wire shape only."""

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
    email: str
    full_name: str | None
    permissions: list[str]
