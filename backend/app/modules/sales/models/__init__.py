"""Sales models package (STRUCTURE §3): a models/ package from the start because the customer master
and the pricing tables together exceed the 400-line cap (the finance/inventory/procurement
precedent). Re-exported here so call sites use one import (``from app.modules.sales.models import
Customer``).

- ``customers``: the ``CustomerGroup`` grouping master + the ``Customer`` entity (7.1).
- ``pricing``: the ``PriceList`` condition header + its ``PriceListItem`` base prices (7.1).
- ``orders``: the ``Quote`` + ``QuoteLine`` and ``SalesOrder`` + ``SalesOrderLine`` O2C documents
  (7.2).
- ``deliveries``: the ``Delivery`` + ``DeliveryLine`` outbound fulfilment documents (7.3).

The invoice document tables (7.4) will add their own file here.
"""

from app.modules.sales.models.customers import Customer, CustomerGroup
from app.modules.sales.models.deliveries import Delivery, DeliveryLine
from app.modules.sales.models.orders import (
    Quote,
    QuoteLine,
    SalesOrder,
    SalesOrderLine,
)
from app.modules.sales.models.pricing import PriceList, PriceListItem

__all__ = [
    "Customer",
    "CustomerGroup",
    "Delivery",
    "DeliveryLine",
    "PriceList",
    "PriceListItem",
    "Quote",
    "QuoteLine",
    "SalesOrder",
    "SalesOrderLine",
]
