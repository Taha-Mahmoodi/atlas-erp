"""Shared Pydantic v2 bases: API model config, D-014 error envelope, list envelope."""

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
