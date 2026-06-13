"""Sales module — the fourth business module (PLAN 7), sitting above inventory + finance in the
dependency order (STRUCTURE §5: sales may read finance/queries AND inventory/queries downward;
everyone above sales reads sales/queries).

PLAN 7.1 OPENS the module with the customer master and the condition-style pricing engine:

- the ``Customer`` entity (customer code, name, status, default currency, payment terms, credit
  limit, contact fields) and an optional ``CustomerGroup`` master (a lean code/name table pricing
  keys on);
- condition-style price lists: a ``PriceList`` (currency + optional customer group + date window +
  priority + status) carrying ``PriceListItem`` rows (one base unit price per item), resolved by
  ``service.price_resolution.resolve_price`` / ``queries.resolve_price`` — the deterministic
  best-match picker the order module (7.2) prices lines through.

The quote → order → delivery → invoice chain (7.2–7.4) lands later; this package grows in place.

**Cross-module ownership (D-029).** Sales OWNS the customer entity. Finance AR already stores a
customer on each invoice/receipt as an OPAQUE ``partner_id`` (plus a denormalized ``partner_name``,
NO FK) — and that ``partner_id`` IS this module's ``Customer.id``. Finance never FK-references the
customer master (it is below sales); sales resolves an invoice's ``partner_id`` back to a customer
via ``queries.get_customer_for_partner`` — the exact mirror of the procurement vendor↔partner_id
link. Inventory items a price-list item points at are validated by opaque id through
``inventory/queries.item_exists`` — never a cross-module FK. The default currency is validated
against finance's catalog via ``finance/queries.currency_exists``.

Importing this package registers the module's permission keys in the core RBAC catalog
(constants.py runs ``register_permissions`` at import), as finance/inventory/procurement do.
"""

from app.modules.sales import (
    constants as _constants,  # noqa: F401 - import-time perm registration
)
