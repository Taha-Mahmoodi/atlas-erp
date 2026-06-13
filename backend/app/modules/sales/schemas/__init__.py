"""Sales request/response schemas package (Pydantic v2, ApiModel base).

Split into a package at the 400-line cap when PLAN 7.2's quote → order schemas landed (STRUCTURE
§8.4, the finance precedent). Re-exported here so ``from app.modules.sales.schemas import
CustomerCreate`` / ``QuoteCreate`` is one import surface — the router + service + test factories use
that surface, so the split is an internal detail.

- ``masters``: customer master + customer groups + price lists + the price-quote response (7.1).
- ``orders``: quote + order create/update/read/filter (+ lines), the action payloads, and the
  ATP-check schemas (7.2).
- ``deliveries``: delivery create/read/filter (+ lines) — the outbound fulfilment document (7.3).
- ``billing``: billing create/read/filter (+ lines) — the O2C invoicing document (7.4).
- ``returns``: return create/read/filter (+ lines) — the RMA reverse-O2C document (7.4).
"""

from app.modules.sales.schemas.billing import (
    BillingCreate,
    BillingDetail,
    BillingFilter,
    BillingLineCreate,
    BillingLineRead,
    BillingRead,
)
from app.modules.sales.schemas.deliveries import (
    DeliveryCreate,
    DeliveryDetail,
    DeliveryFilter,
    DeliveryLineCreate,
    DeliveryLineRead,
    DeliveryRead,
)
from app.modules.sales.schemas.masters import (
    CustomerCreate,
    CustomerFilter,
    CustomerGroupCreate,
    CustomerGroupRead,
    CustomerGroupUpdate,
    CustomerRead,
    CustomerUpdate,
    PriceListCreate,
    PriceListFilter,
    PriceListItemCreate,
    PriceListItemRead,
    PriceListRead,
    PriceListUpdate,
    PriceQuoteRead,
)
from app.modules.sales.schemas.orders import (
    AtpCheckRequest,
    AtpCheckResponse,
    AtpLineRequest,
    AtpLineResult,
    ConvertQuoteToOrder,
    QuoteCreate,
    QuoteDetail,
    QuoteFilter,
    QuoteLineCreate,
    QuoteLineRead,
    QuoteRead,
    QuoteUpdate,
    SalesOrderCreate,
    SalesOrderDetail,
    SalesOrderFilter,
    SalesOrderLineCreate,
    SalesOrderLineRead,
    SalesOrderRead,
    SalesOrderUpdate,
)
from app.modules.sales.schemas.returns import (
    ReturnCreate,
    ReturnDetail,
    ReturnFilter,
    ReturnLineCreate,
    ReturnLineRead,
    ReturnRead,
)

__all__ = [
    "AtpCheckRequest",
    "AtpCheckResponse",
    "AtpLineRequest",
    "AtpLineResult",
    "BillingCreate",
    "BillingDetail",
    "BillingFilter",
    "BillingLineCreate",
    "BillingLineRead",
    "BillingRead",
    "ConvertQuoteToOrder",
    "CustomerCreate",
    "CustomerFilter",
    "CustomerGroupCreate",
    "CustomerGroupRead",
    "CustomerGroupUpdate",
    "CustomerRead",
    "CustomerUpdate",
    "DeliveryCreate",
    "DeliveryDetail",
    "DeliveryFilter",
    "DeliveryLineCreate",
    "DeliveryLineRead",
    "DeliveryRead",
    "PriceListCreate",
    "PriceListFilter",
    "PriceListItemCreate",
    "PriceListItemRead",
    "PriceListRead",
    "PriceListUpdate",
    "PriceQuoteRead",
    "QuoteCreate",
    "QuoteDetail",
    "QuoteFilter",
    "QuoteLineCreate",
    "QuoteLineRead",
    "QuoteRead",
    "QuoteUpdate",
    "ReturnCreate",
    "ReturnDetail",
    "ReturnFilter",
    "ReturnLineCreate",
    "ReturnLineRead",
    "ReturnRead",
    "SalesOrderCreate",
    "SalesOrderDetail",
    "SalesOrderFilter",
    "SalesOrderLineCreate",
    "SalesOrderLineRead",
    "SalesOrderRead",
    "SalesOrderUpdate",
]
