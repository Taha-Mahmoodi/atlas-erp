"""Inventory service package (split per STRUCTURE §3: one file per aggregate, each <400 lines —
the single service.py reached the cap when PLAN 5.1 landed, the same precedent as finance/service).

The router and other callers import service functions from this package surface, so the split into
``categories``, ``uoms``, ``items`` and ``conversions`` (the last also owns the pure
``convert_quantity`` helper) is an internal detail. Re-exported here so call sites use one import
(``from app.modules.inventory import service`` then ``service.create_item(...)``).
"""

from app.modules.inventory.service.categories import (
    create_category,
    get_category,
    list_categories,
    update_category,
)
from app.modules.inventory.service.conversions import (
    convert_quantity,
    create_conversion,
    get_conversion_factors,
    list_conversions,
)
from app.modules.inventory.service.items import (
    create_item,
    get_item,
    list_items,
    update_item,
)
from app.modules.inventory.service.uoms import (
    create_uom,
    get_uom,
    list_uoms,
    update_uom,
)

__all__ = [
    "convert_quantity",
    "create_category",
    "create_conversion",
    "create_item",
    "create_uom",
    "get_category",
    "get_conversion_factors",
    "get_item",
    "get_uom",
    "list_categories",
    "list_conversions",
    "list_items",
    "list_uoms",
    "update_category",
    "update_item",
    "update_uom",
]
