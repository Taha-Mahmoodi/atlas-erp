"""Procurement module — the third business module (PLAN 6), sitting above inventory in the
dependency order (STRUCTURE §5: procurement may read finance/queries AND inventory/queries
downward; everyone above procurement reads procurement/queries).

PLAN 6.1 OPENS the module with the vendor master: the ``Vendor`` entity (vendor code, name,
status, default currency, payment terms, contact fields) plus the v1 "approved items"
info-record-lite (``VendorApprovedItem`` — the vendor↔item link, no time-dependent pricing per the
s4hana-parity Procurement section). The P2P chain (requisition → RFQ → PO → goods receipt → 3-way
match) lands in PLAN 6.2–6.4; this package grows in place.

**Cross-module ownership (D-029).** Procurement OWNS the vendor entity. Finance AP already stores a
vendor on each bill/payment as an OPAQUE ``partner_id`` (plus a denormalized ``partner_name``,
NO FK) — and that ``partner_id`` IS this module's ``Vendor.id``. Finance never FK-references the
vendor master (it is below procurement); procurement resolves a bill's ``partner_id`` back to a
vendor via ``queries.get_vendor_for_partner``. Inventory items an approved-item points at are
validated by opaque id through ``inventory/queries.item_exists`` — never a cross-module FK.

Importing this package registers the module's permission keys in the core RBAC catalog
(constants.py runs ``register_permissions`` at import), as finance/inventory/admin/core do.
"""

from app.modules.procurement import (
    constants as _constants,  # noqa: F401 - import-time perm registration
)
