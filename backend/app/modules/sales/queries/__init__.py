"""Sales' cross-module read interface (STRUCTURE §5).

Sales sits above inventory and finance in the dependency order: the O2C documents in 7.2–7.4
(quote → order → delivery → invoice) and finance AR reporting read THIS file to resolve customer
state + prices synchronously; sales imports finance/queries + inventory/queries downward. Keep this
surface thin and stable — it is a contract; it is the ONLY sales file other modules import.

The central D-029 link: finance AR stores a customer on each invoice/receipt as an opaque
``partner_id`` (no FK). ``get_customer_for_partner`` resolves that ``partner_id`` back to a
``Customer`` so AR aging / reporting can render the customer's name and payment terms — the
``partner_id`` IS the ``Customer.id``, so it is a thin alias over ``get_customer`` named for the
reporting intent (the exact mirror of procurement's ``get_vendor_for_partner``).

The PRICE RESOLVER is exposed too: ``resolve_price`` (the public entry 7.2 prices lines through)
delegates to ``service/price_resolution.resolve_price`` (the best-match picker, D-043), keeping the
rule that other modules import only this file.

The ORDER reads 7.3/7.4 call — ``get_sales_order``, ``get_order_for_delivery`` /
``get_order_for_invoice``, the per-line open-quantity helpers ``so_line_open_to_deliver`` /
``_to_invoice`` / ``_to_return`` (ordered/delivered/invoiced minus the next stage), and the ATP +
credit helpers the confirm gate uses (``committed_quantity``, ``atp_check``,
``open_confirmed_order_value``, ``customer_open_ar``) — the last two making SANCTIONED downward
cross-module reads (inventory on-hand, procurement on-order, finance open AR).

The single ``queries.py`` reached the 400-line cap, so it split along the §8.4 package rule: the
customer-master reads + price resolver live in ``customers.py``, the sales-order header/line reads +
open-quantity helpers in ``orders.py``, the ATP + credit-exposure reads in ``availability.py``. All
are re-exported here, so every ``from app.modules.sales.queries import X`` import — and every
``from app.modules.sales import queries; queries.X(...)`` call — keeps working from one surface.

Every function takes an explicit ``tenant_id`` and runs under the caller's tenant context, so the
D-007 filter applies on top of the explicit predicate — ordinary tenant-scoped reads, not a bypass.
"""

from app.modules.sales.queries.availability import (
    AtpResult,
    atp_check,
    committed_quantity,
    customer_open_ar,
    open_confirmed_order_value,
    open_demand_item_ids,
)
from app.modules.sales.queries.customers import (
    customer_credit_limit,
    customer_default_currency,
    customer_exists,
    customer_payment_terms_days,
    customer_status,
    get_customer,
    get_customer_for_partner,
    resolve_price,
)
from app.modules.sales.queries.dashboards import (
    OnTimeDelivery,
    OpenOrders,
    on_time_delivery,
    open_sales_orders,
)
from app.modules.sales.queries.orders import (
    get_order_for_delivery,
    get_order_for_invoice,
    get_sales_order,
    so_line_open_to_deliver,
    so_line_open_to_invoice,
    so_line_open_to_return,
)

__all__ = [
    "AtpResult",
    "OnTimeDelivery",
    "OpenOrders",
    "atp_check",
    "committed_quantity",
    "customer_credit_limit",
    "customer_default_currency",
    "customer_exists",
    "customer_open_ar",
    "customer_payment_terms_days",
    "customer_status",
    "get_customer",
    "get_customer_for_partner",
    "get_order_for_delivery",
    "get_order_for_invoice",
    "get_sales_order",
    "on_time_delivery",
    "open_confirmed_order_value",
    "open_demand_item_ids",
    "open_sales_orders",
    "resolve_price",
    "so_line_open_to_deliver",
    "so_line_open_to_invoice",
    "so_line_open_to_return",
]
