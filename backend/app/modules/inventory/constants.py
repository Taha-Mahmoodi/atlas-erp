"""Inventory constants (STRUCTURE §3): enums (UPPER_SNAKE values stored as strings) and the
permission keys, registered into the core RBAC catalog at import (D-009).

Started as a SINGLE file (STRUCTURE §8.4: split into a constants/ package only at the 400-line
cap, the finance precedent); it sits well under that for PLAN 5.1.

Item codes are USER-SUPPLIED and unique per tenant (the ``UNIQUE(tenant_id, item_code)`` on
inv_items) — mirroring how chart-of-accounts codes work (Account.code is required on create, not
auto-numbered). So inventory declares NO number sequence here: masters carry no gapless document
number (those are for journal entries / orders / receipts in D-012). When stock *moves* land in
PLAN 5.2 they register documents and claim numbers; the item master itself does not.
"""

from enum import StrEnum

from app.core.rbac import register_permissions


class ItemType(StrEnum):
    """What an item IS, which decides whether it carries stock (D-020).

    - STOCKED: a physical good tracked in inventory — the only type that participates in stock
      moves, costing and lot/serial tracking.
    - NON_STOCKED: a purchasable/sellable good NOT held in inventory (e.g. drop-ship, expensed
      supplies) — no on-hand quantity, no costing layer.
    - SERVICE: a non-physical line item (labour, fees) — never stocked, never tracked.

    The service rejects tracking/costing participation for NON_STOCKED/SERVICE so the invariant
    "only STOCKED items have stock" holds from the masters up (validated again when moves land)."""

    STOCKED = "STOCKED"
    NON_STOCKED = "NON_STOCKED"
    SERVICE = "SERVICE"


class CostingMethod(StrEnum):
    """How a stocked item is valued (D-020). Defaulted onto the item FROM its category at create
    but STORED on the item, because D-020 changes it only while no stock exists and the item is
    the costing unit. The moving-average valuation table and FIFO cost layers arrive in PLAN 5.3;
    5.1 only records the method so receipts know which engine to use."""

    MOVING_AVERAGE = "MOVING_AVERAGE"
    FIFO = "FIFO"


class TrackingMode(StrEnum):
    """Whether a stocked item's units are individually identified (parity: batch/serial mgmt).

    - NONE: fungible — quantity only (the default).
    - LOT: grouped by lot/batch code; one lot row per received batch (inv_lots), created at
      receipt (5.2+).
    - SERIAL: each unit uniquely identified; one inv_serials row per unit, created at receipt.

    Tracking is PER ITEM and only meaningful for STOCKED items — the service forbids a non-NONE
    mode on NON_STOCKED/SERVICE items."""

    NONE = "NONE"
    LOT = "LOT"
    SERIAL = "SERIAL"


class LotStatus(StrEnum):
    """Lifecycle of a lot/batch instance (parity: batch management). For 5.1 the table merely
    EXISTS — lots are created during receipts (5.2+); AVAILABLE is the default a receipt sets,
    the others are reached by later quality/expiry flows. No dead CRUD now (masters-only)."""

    AVAILABLE = "AVAILABLE"
    BLOCKED = "BLOCKED"
    CONSUMED = "CONSUMED"


class SerialStatus(StrEnum):
    """Lifecycle of a serial-number instance (parity: serial management). Like LotStatus, the
    table exists for 5.1 and is populated at receipt (5.2+): IN_STOCK on receipt, ISSUED when
    the unit leaves, BLOCKED by quality holds."""

    IN_STOCK = "IN_STOCK"
    ISSUED = "ISSUED"
    BLOCKED = "BLOCKED"


# --- Permissions (D-009): one key per guarded endpoint action -----------------
INVENTORY_ITEM_READ = "inventory.item.read"
INVENTORY_ITEM_MANAGE = "inventory.item.manage"
INVENTORY_CATEGORY_READ = "inventory.category.read"
INVENTORY_CATEGORY_MANAGE = "inventory.category.manage"
INVENTORY_UOM_READ = "inventory.uom.read"
INVENTORY_UOM_MANAGE = "inventory.uom.manage"

register_permissions(
    INVENTORY_ITEM_READ,
    INVENTORY_ITEM_MANAGE,
    INVENTORY_CATEGORY_READ,
    INVENTORY_CATEGORY_MANAGE,
    INVENTORY_UOM_READ,
    INVENTORY_UOM_MANAGE,
    descriptions={
        INVENTORY_ITEM_READ: "Read items and their UoM conversions",
        INVENTORY_ITEM_MANAGE: "Create and edit items and their UoM conversions",
        INVENTORY_CATEGORY_READ: "Read item categories",
        INVENTORY_CATEGORY_MANAGE: "Create and edit item categories",
        INVENTORY_UOM_READ: "Read units of measure",
        INVENTORY_UOM_MANAGE: "Create and edit units of measure",
    },
)
