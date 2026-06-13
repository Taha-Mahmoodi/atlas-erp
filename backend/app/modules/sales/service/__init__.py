"""Sales service package (STRUCTURE §3: split per aggregate, each <400 lines — a service/ package
from the start because the customer master, customer groups, pricing CRUD and the resolver are
separate concerns).

The router and test factories import service functions from this package surface (``from
app.modules.sales import service`` then ``service.create_customer(...)``), so the split is an
internal detail. Re-exported here so call sites use one import.

- ``customers``: customer master CRUD (7.1).
- ``customer_groups``: customer-group CRUD (7.1).
- ``pricing``: price-list + price-list-item CRUD (7.1).
- ``price_resolution``: the deterministic condition resolver ``resolve_price`` (7.1, D-043) — also
  the public surface ``sales/queries.resolve_price`` exposes to the order module (7.2).
- ``quotes``: sales-quotation CRUD + send/accept/reject/cancel/expiry (7.2).
- ``orders``: sales-order create/update/cancel + reads + the shared writer (7.2).
- ``order_confirm``: the confirm gate (ATP + credit) + credit-release (7.2, D-044).
- ``conversions``: quote → order conversion (7.2).
- ``deliveries``: outbound-delivery create/cancel (7.3, D-045).
- ``delivery_post``: outbound-delivery post — the stock-issue → COGS seam (7.3, D-045).
- ``delivery_reads``: delivery list + header/line point reads (7.3).
"""

from app.modules.sales.service.conversions import convert_quote_to_order
from app.modules.sales.service.customer_groups import (
    create_customer_group,
    get_customer_group,
    list_customer_groups,
    update_customer_group,
)
from app.modules.sales.service.customers import (
    create_customer,
    get_customer,
    list_customers,
    update_customer,
)
from app.modules.sales.service.deliveries import (
    cancel_delivery,
    create_delivery,
)
from app.modules.sales.service.delivery_post import post_delivery
from app.modules.sales.service.delivery_reads import (
    deliveries_for_order,
    get_delivery,
    get_delivery_lines,
    list_deliveries,
)
from app.modules.sales.service.order_confirm import (
    ConfirmResult,
    confirm_order,
    release_credit,
)
from app.modules.sales.service.orders import (
    cancel_sales_order,
    create_sales_order,
    get_sales_order,
    get_sales_order_lines,
    list_sales_orders,
    update_sales_order,
)
from app.modules.sales.service.price_resolution import ResolvedPrice, resolve_price
from app.modules.sales.service.pricing import (
    add_price_list_item,
    create_price_list,
    get_price_list,
    list_price_list_items,
    list_price_lists,
    remove_price_list_item,
    update_price_list,
)
from app.modules.sales.service.quotes import (
    accept_quote,
    cancel_quote,
    create_quote,
    get_quote,
    get_quote_lines,
    list_quotes,
    mark_expired_if_lapsed,
    mark_quote_expired,
    reject_quote,
    send_quote,
    update_quote,
)

__all__ = [
    "ConfirmResult",
    "ResolvedPrice",
    "accept_quote",
    "add_price_list_item",
    "cancel_delivery",
    "cancel_quote",
    "cancel_sales_order",
    "confirm_order",
    "convert_quote_to_order",
    "create_customer",
    "create_customer_group",
    "create_delivery",
    "create_price_list",
    "create_quote",
    "create_sales_order",
    "deliveries_for_order",
    "get_customer",
    "get_customer_group",
    "get_delivery",
    "get_delivery_lines",
    "get_price_list",
    "get_quote",
    "get_quote_lines",
    "get_sales_order",
    "get_sales_order_lines",
    "list_customer_groups",
    "list_customers",
    "list_deliveries",
    "list_price_list_items",
    "list_price_lists",
    "list_quotes",
    "list_sales_orders",
    "post_delivery",
    "mark_expired_if_lapsed",
    "mark_quote_expired",
    "reject_quote",
    "release_credit",
    "remove_price_list_item",
    "resolve_price",
    "send_quote",
    "update_customer",
    "update_customer_group",
    "update_price_list",
    "update_quote",
    "update_sales_order",
]
