"""BOM request/response schemas (Pydantic v2, ApiModel base) for PLAN 8.1.

A BOM is a header (``Bom``) + components. Components are a SUB-RESOURCE created/listed/deleted under
the BOM (their own Create/Read schemas), NOT nested into the header create — keeping each operation
small and letting components be added incrementally while the BOM is DRAFT (D-047). The BOM header's
status is server-driven (DRAFT at create, changed via activate/deactivate actions), so it is absent
from Create/Update. ``status`` on the header read is a ``BomStatus`` enum (ApiModel serializes it as
its UPPER_SNAKE string). Quantities/scrap are ``Decimal`` strings (D-015).
"""

import uuid
from datetime import datetime
from decimal import Decimal

from app.core.schemas import ApiModel
from app.modules.manufacturing.constants import BomStatus


class BomCreate(ApiModel):
    """Create a BOM header (D-047). Identity is ``(item_id, version)`` — ``item_id`` is the opaque
    inventory PARENT item the BOM produces, ``version`` a user-supplied string. ``base_quantity``
    (> 0) is how many parent units the BOM yields; ``uom_id`` is the parent's opaque UoM id. Born
    DRAFT (status is server-driven); components are added afterwards via the nested endpoint."""

    item_id: uuid.UUID
    version: str
    name: str
    base_quantity: Decimal = Decimal(1)
    uom_id: uuid.UUID
    notes: str | None = None


class BomUpdate(ApiModel):
    """Partial update of a BOM header — only while DRAFT (the service enforces it). ``item_id`` and
    ``version`` are immutable (they ARE the identity) and so are absent; ``status``/``is_default``
    change only through the activate/deactivate actions, never a blind PATCH."""

    name: str | None = None
    base_quantity: Decimal | None = None
    uom_id: uuid.UUID | None = None
    notes: str | None = None


class BomRead(ApiModel):
    id: uuid.UUID
    item_id: uuid.UUID
    version: str
    name: str
    status: BomStatus
    base_quantity: Decimal
    uom_id: uuid.UUID
    is_default: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime


class BomFilter(ApiModel):
    """List filters for the BOMs endpoint. None means "no constraint"; folded into the cursor's
    filter fingerprint so a cursor cannot cross filtered views."""

    item_id: uuid.UUID | None = None
    status: BomStatus | None = None


# --- Components (sub-resource under a BOM) -------------------------------------


class BomComponentCreate(ApiModel):
    """Add a component line to a DRAFT BOM (D-047). ``component_item_id`` is the opaque inventory
    item consumed — it MUST differ from the BOM's parent item (no self-reference). ``quantity_per``
    (> 0) is the quantity per the header's ``base_quantity`` of parent; ``uom_id`` is the
    component's opaque UoM id; ``scrap_percent`` (>= 0) is the waste allowance. ``line_number`` is
    OPTIONAL — the service appends the next line when omitted (the bom_id comes from the path)."""

    component_item_id: uuid.UUID
    quantity_per: Decimal
    uom_id: uuid.UUID
    scrap_percent: Decimal = Decimal(0)
    line_number: int | None = None
    notes: str | None = None


class BomComponentRead(ApiModel):
    id: uuid.UUID
    bom_id: uuid.UUID
    line_number: int
    component_item_id: uuid.UUID
    quantity_per: Decimal
    uom_id: uuid.UUID
    scrap_percent: Decimal
    notes: str | None
    created_at: datetime
