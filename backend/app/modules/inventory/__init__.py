"""Inventory module — the second business module (PLAN 5), sitting above finance in the
dependency order (STRUCTURE §5: inventory may read finance/queries; everyone above inventory
reads inventory/queries).

PLAN 5.1 lays the master-data foundation: item categories (carrying the default costing method
and the OPAQUE GL-account wiring COGS posting will need, D-020/D-029), units of measure and
per-item UoM conversions, the item master (typed STOCKED/NON_STOCKED/SERVICE with a per-item
base UoM, costing method and lot/serial tracking mode), and the lot/serial master tables
(defined now, populated by receipts in 5.2+). Stock moves, costing and physical counts land in
PLAN 5.2-5.4 — this package grows in place.

Importing this package registers the module's permission keys in the core RBAC catalog
(constants.py runs ``register_permissions`` at import), the same way finance/admin/core do.
"""

from app.modules.inventory import (
    constants as _constants,  # noqa: F401 - import-time perm registration
)
