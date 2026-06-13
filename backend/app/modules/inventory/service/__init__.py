"""Inventory service package (split per STRUCTURE §3: one file per aggregate, each <400 lines —
the single service.py reached the cap when PLAN 5.1 landed, the same precedent as finance/service).

The router and other callers import service functions from this package surface, so the split into
``categories``, ``uoms``, ``items``, ``conversions`` (5.1) and ``warehouses``, ``bins``,
``stock_moves``/``stock_quants`` (5.2) is an internal detail. Re-exported here so call sites use one
import (``from app.modules.inventory import service`` then ``service.create_move(...)``).
"""

from app.modules.inventory.service.bins import (
    create_bin,
    get_bin,
    list_bins,
    update_bin,
)
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
from app.modules.inventory.service.stock_moves import create_move, reverse_move
from app.modules.inventory.service.stock_quants import InsufficientStockError
from app.modules.inventory.service.stock_reads import get_move, list_moves, list_on_hand
from app.modules.inventory.service.uoms import (
    create_uom,
    get_uom,
    list_uoms,
    update_uom,
)
from app.modules.inventory.service.warehouses import (
    create_warehouse,
    get_warehouse,
    list_warehouses,
    update_warehouse,
)

__all__ = [
    "InsufficientStockError",
    "convert_quantity",
    "create_bin",
    "create_category",
    "create_conversion",
    "create_item",
    "create_move",
    "create_uom",
    "create_warehouse",
    "get_bin",
    "get_category",
    "get_conversion_factors",
    "get_item",
    "get_move",
    "get_uom",
    "get_warehouse",
    "list_bins",
    "list_categories",
    "list_conversions",
    "list_items",
    "list_moves",
    "list_on_hand",
    "list_uoms",
    "list_warehouses",
    "reverse_move",
    "update_bin",
    "update_category",
    "update_item",
    "update_uom",
    "update_warehouse",
]
