"""Manufacturing module (PLAN 8) — the fifth business module.

PLAN 8.1 opens it with the PP MASTER DATA: multi-level versioned BOMs, work centers, and routings
(s4hana-parity PP: BOMs multi-level+versioned, work centers, routings all = FULL). Production
orders (8.2) and the MRP run + rough capacity check (8.3) build on these masters.

Manufacturing sits ABOVE inventory and procurement/sales in the dependency order (STRUCTURE §5): it
may import ``finance/queries`` and ``inventory/queries`` DOWNWARD (D-029) — BOM components and
routing operations reference inventory items by OPAQUE id (validated via inventory/queries), a work
centre's optional cost centre by opaque finance id (validated via finance/queries) — and exposes its
own ``manufacturing/queries.py`` as the only file the modules above it (8.2/8.3) import.
"""
