"""Procurement constants (STRUCTURE §3): the vendor-master enums and the permission keys,
registered into the core RBAC catalog at import (D-009).

Started as a SINGLE file (STRUCTURE §8.4: split into a constants/ package only at the 400-line
cap, the finance precedent); PLAN 6.1 sits well under that.

**Payment-terms modeling (decided here).** A vendor carries ``payment_terms_days`` — a plain
integer net-days value (30 = NET30) — NOT a separate terms master/value-set. This matches how AP
already computes a bill's due date (bill_date + net days) and keeps v1 simple; richer term
schedules (e.g. 2/10 NET30 early-payment discounts, multi-instalment plans) are deferred per the
parity doc and would arrive as a terms entity referenced from the vendor. The field is stored with
a CHECK >= 0 on the vendor.

**Vendor codes are USER-SUPPLIED and unique per tenant** (the ``UNIQUE(tenant_id, vendor_code)`` on
proc_vendors) — mirroring inventory ``item_code`` and the finance account ``code``: a vendor MASTER
carries no gapless document number (a code, not a number). The P2P DOCUMENTS in 6.2+ (requisitions,
POs, GRs) DO claim gapless numbers — a posted document in the D-012 sense — but the master does not.
"""

from enum import StrEnum

from app.core.rbac import register_permissions


class VendorStatus(StrEnum):
    """A vendor's lifecycle / usability state (parity: vendor master block levels).

    - ACTIVE: usable — new purchase orders may name this vendor (the only state 6.2+ accepts).
    - BLOCKED: temporarily barred — kept for history and existing open documents, but the P2P
      chain (6.2) refuses to raise a NEW PO against it (a soft block; the vendor can be unblocked
      back to ACTIVE).
    - INACTIVE: retired — no new business, retained for reporting and existing AP history.

    Transitions are unrestricted between the three (ACTIVE↔BLOCKED↔INACTIVE all allowed): a block
    is reversible and a retired vendor can be reactivated. The only rule the service enforces is
    that the target is a valid VendorStatus; no terminal state, because vendor history must stay
    referenceable and a mistaken retire/block must be undoable (the append-only ledger lives in
    finance AP, not here)."""

    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    INACTIVE = "INACTIVE"


# The default net-days a vendor is created with when the payload omits it (NET30 — the common
# commercial default; AP's due-date math is bill_date + this many days). Stored on the vendor.
DEFAULT_PAYMENT_TERMS_DAYS = 30


# --- Permissions (D-009): one key per guarded endpoint action -----------------
# Two keys: read the vendor master (+ its approved items) vs create/edit it. Approved-item
# management is a vendor-master edit, so it rides VENDOR_MANAGE rather than a third key — adding an
# approved item is configuring the vendor, not a distinct privileged action (the inventory
# item/uom-conversion precedent: nested config shares the parent's manage key).
PROCUREMENT_VENDOR_READ = "procurement.vendor.read"
PROCUREMENT_VENDOR_MANAGE = "procurement.vendor.manage"

register_permissions(
    PROCUREMENT_VENDOR_READ,
    PROCUREMENT_VENDOR_MANAGE,
    descriptions={
        PROCUREMENT_VENDOR_READ: "Read vendors and their approved items",
        PROCUREMENT_VENDOR_MANAGE: "Create and edit vendors and their approved items",
    },
)
