"""Work-centre request/response schemas (Pydantic v2, ApiModel base) for PLAN 8.1.

Read schemas mirror the model field-for-field in snake_case; ``is_active`` and the decimals
(capacity hours, efficiency percent) are ``Decimal`` in Python, serialized as strings (D-015).
Create/Update carry only client-settable fields; ids and timestamps are server-owned. ``code`` is
immutable after creation (routings reference work centres) and so is absent from Update.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from app.core.schemas import ApiModel


class WorkCenterCreate(ApiModel):
    """Create a work centre. ``code`` is user-supplied + unique per tenant. ``cost_center_id`` is an
    OPTIONAL opaque finance cost-centre id — validated to exist in finance when set (D-029).
    ``capacity_hours_per_day`` (>= 0) feeds 8.3's rough capacity check; ``efficiency_percent`` (> 0,
    default 100) scales throughput."""

    code: str
    name: str
    description: str | None = None
    cost_center_id: uuid.UUID | None = None
    capacity_hours_per_day: Decimal = Decimal(0)
    efficiency_percent: Decimal = Decimal(100)
    is_active: bool = True


class WorkCenterUpdate(ApiModel):
    """Partial update — every field optional; ``code`` is immutable (operations reference the work
    centre) and so is deliberately absent. A changed ``cost_center_id`` is re-validated."""

    name: str | None = None
    description: str | None = None
    cost_center_id: uuid.UUID | None = None
    capacity_hours_per_day: Decimal | None = None
    efficiency_percent: Decimal | None = None
    is_active: bool | None = None


class WorkCenterRead(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    cost_center_id: uuid.UUID | None
    capacity_hours_per_day: Decimal
    efficiency_percent: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime


class WorkCenterFilter(ApiModel):
    """List filter for the work-centre endpoint. None means "no constraint"; folded into the
    cursor's filter fingerprint so a cursor cannot cross filtered views."""

    is_active: bool | None = None
