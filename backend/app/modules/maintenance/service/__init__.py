"""Maintenance service package (STRUCTURE §3: one file per aggregate, each <400 lines — the
manufacturing/inventory precedent). The router and other callers import from this package surface,
so the split into ``equipment``, ``orders`` and ``plans`` is an internal detail. Re-exported here so
call sites use one import (``from app.modules.maintenance import service`` then
``service.create_corrective(...)``).
"""

from app.modules.maintenance.service.equipment import (
    create_equipment,
    get_equipment,
    list_equipment,
    update_equipment,
)
from app.modules.maintenance.service.orders import (
    cancel_order,
    complete_order,
    create_corrective,
    create_generated_order,
    get_maintenance_order,
    list_maintenance_orders,
    schedule_order,
    start_order,
    update_order,
)
from app.modules.maintenance.service.plans import (
    advance_due_date,
    create_plan,
    get_maintenance_plan,
    list_plans,
    run_preventive_maintenance,
    set_plan_status,
    update_plan,
)

__all__ = [
    "advance_due_date",
    "cancel_order",
    "complete_order",
    "create_corrective",
    "create_equipment",
    "create_generated_order",
    "create_plan",
    "get_equipment",
    "get_maintenance_order",
    "get_maintenance_plan",
    "list_equipment",
    "list_maintenance_orders",
    "list_plans",
    "run_preventive_maintenance",
    "schedule_order",
    "set_plan_status",
    "start_order",
    "update_equipment",
    "update_order",
    "update_plan",
]
