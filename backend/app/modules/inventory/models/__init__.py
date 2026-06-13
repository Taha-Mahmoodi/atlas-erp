"""Inventory models package (STRUCTURE §3: split into models/ once PLAN 5.2's stock tables would
have pushed the combined models.py over the 400-line cap, the finance models/ precedent).

Re-exports every model so ``from app.modules.inventory.models import Item`` (and ``StockMove``,
``Warehouse``, ...) keep working from ONE surface, and so every importer (alembic env.py, the
tenancy mapper-enumeration suite) registers all tables on ``Base.metadata``.

- ``masters``: item categories, UoMs, conversions, the item master, lot/serial instances (5.1).
- ``stock``: warehouses, bins, the stock-move ledger (the quantity SSOT) and the maintained
  on-hand quant projection (5.2, D-020/D-036).
"""

from app.modules.inventory.models.masters import (
    Item,
    ItemCategory,
    Lot,
    SerialNumber,
    Uom,
    UomConversion,
)
from app.modules.inventory.models.stock import Bin, StockMove, StockQuant, Warehouse

__all__ = [
    "Bin",
    "Item",
    "ItemCategory",
    "Lot",
    "SerialNumber",
    "StockMove",
    "StockQuant",
    "Uom",
    "UomConversion",
    "Warehouse",
]
