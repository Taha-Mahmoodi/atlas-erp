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
"""

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

__all__ = [
    "ResolvedPrice",
    "add_price_list_item",
    "create_customer",
    "create_customer_group",
    "create_price_list",
    "get_customer",
    "get_customer_group",
    "get_price_list",
    "list_customer_groups",
    "list_customers",
    "list_price_list_items",
    "list_price_lists",
    "remove_price_list_item",
    "resolve_price",
    "update_customer",
    "update_customer_group",
    "update_price_list",
]
