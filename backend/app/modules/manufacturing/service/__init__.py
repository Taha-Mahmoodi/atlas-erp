"""Manufacturing service package (STRUCTURE §3: one file per aggregate, each <400 lines — the
inventory/finance precedent). The router and other callers import from this package surface, so the
split into ``work_centers``, ``boms`` and ``routings`` is an internal detail. Re-exported here so
call sites use one import (``from app.modules.manufacturing import service`` then
``service.create_bom(...)``).
"""

from app.modules.manufacturing.service.boms import (
    activate_bom,
    add_component,
    bom_components_for,
    create_bom,
    deactivate_bom,
    delete_component,
    get_bom,
    list_boms,
    update_bom,
)
from app.modules.manufacturing.service.production_orders import (
    cancel_order,
    create_production_order,
    get_production_order,
    list_production_orders,
    production_order_components,
    production_order_operations,
    release_order,
)
from app.modules.manufacturing.service.production_post import (
    finish_order,
    issue_components,
)
from app.modules.manufacturing.service.routings import (
    activate_routing,
    add_operation,
    create_routing,
    deactivate_routing,
    delete_operation,
    get_routing,
    list_routings,
    routing_operations_for,
    update_routing,
)
from app.modules.manufacturing.service.work_centers import (
    create_work_center,
    get_work_center,
    list_work_centers,
    update_work_center,
)

__all__ = [
    "activate_bom",
    "activate_routing",
    "add_component",
    "add_operation",
    "bom_components_for",
    "cancel_order",
    "create_bom",
    "create_production_order",
    "create_routing",
    "create_work_center",
    "deactivate_bom",
    "deactivate_routing",
    "delete_component",
    "delete_operation",
    "finish_order",
    "get_bom",
    "get_production_order",
    "get_routing",
    "get_work_center",
    "issue_components",
    "list_boms",
    "list_production_orders",
    "list_routings",
    "list_work_centers",
    "production_order_components",
    "production_order_operations",
    "release_order",
    "routing_operations_for",
    "update_bom",
    "update_routing",
    "update_work_center",
]
