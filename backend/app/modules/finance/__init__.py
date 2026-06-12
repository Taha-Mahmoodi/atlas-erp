"""Finance module — the first business module and the bottom of the dependency order
(STRUCTURE §5: everyone may read finance/queries.py, finance reads no other module).

PLAN 4.1 lays the schema foundation: the chart of accounts (account-type model per D-021,
from which all financial statements later project) and fiscal years/periods with the
open/close lifecycle (D-018). The universal journal (D-017), the DB-level period-posting
trigger (D-018), AP/AR, payments and FX land in PLAN 4.2-4.10 — this package grows in place.

Importing this package registers the module's permission keys in the core RBAC catalog
(constants.py runs ``register_permissions`` at import), the same way admin/core do.
"""

from app.modules.finance import (
    constants as _constants,  # noqa: F401 - import-time perm registration
)
