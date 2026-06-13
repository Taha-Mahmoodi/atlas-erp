"""Routing request/response schemas (Pydantic v2, ApiModel base) for PLAN 8.1.

A routing is a header (``Routing``) + operations. Operations are a SUB-RESOURCE under the routing
(the BOM-component shape), added incrementally while the routing is DRAFT (D-047). The header status
is server-driven (DRAFT at create, changed via activate/deactivate), so it is absent from
Create/Update. Times are MINUTES as ``Decimal`` strings (D-015): ``setup_time_minutes`` fixed per
order, ``run_time_minutes_per_unit`` per produced unit.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from app.core.schemas import ApiModel
from app.modules.manufacturing.constants import RoutingStatus


class RoutingCreate(ApiModel):
    """Create a routing header (D-047). Identity ``(item_id, version)`` — ``item_id`` is the opaque
    inventory item this routing makes, ``version`` a user-supplied string. Born DRAFT; operations
    are added afterwards via the nested endpoint."""

    item_id: uuid.UUID
    version: str
    name: str
    notes: str | None = None


class RoutingUpdate(ApiModel):
    """Partial update of a routing header — only while DRAFT (the service enforces it). ``item_id``
    and ``version`` are immutable (the identity) and absent; ``status``/``is_default`` change only
    through the activate/deactivate actions."""

    name: str | None = None
    notes: str | None = None


class RoutingRead(ApiModel):
    id: uuid.UUID
    item_id: uuid.UUID
    version: str
    name: str
    status: RoutingStatus
    is_default: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime


class RoutingFilter(ApiModel):
    """List filters for the routings endpoint. None means "no constraint"; folded into the cursor's
    filter fingerprint so a cursor cannot cross filtered views."""

    item_id: uuid.UUID | None = None
    status: RoutingStatus | None = None


# --- Operations (sub-resource under a routing) --------------------------------


class RoutingOperationCreate(ApiModel):
    """Add an operation to a DRAFT routing (D-047). ``work_center_id`` is the work centre the step
    runs on (validated to exist in this tenant). ``setup_time_minutes`` (>= 0) is fixed per order;
    ``run_time_minutes_per_unit`` (>= 0) is per produced unit. ``operation_number`` is OPTIONAL —
    the service appends the next multiple of 10 when omitted (the routing_id comes from the
    path)."""

    work_center_id: uuid.UUID
    description: str | None = None
    setup_time_minutes: Decimal = Decimal(0)
    run_time_minutes_per_unit: Decimal = Decimal(0)
    operation_number: int | None = None
    notes: str | None = None


class RoutingOperationRead(ApiModel):
    id: uuid.UUID
    routing_id: uuid.UUID
    operation_number: int
    work_center_id: uuid.UUID
    description: str | None
    setup_time_minutes: Decimal
    run_time_minutes_per_unit: Decimal
    notes: str | None
    created_at: datetime
