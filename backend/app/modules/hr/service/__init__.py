"""HR service package (STRUCTURE §3: one file per aggregate, each <400 lines — the
manufacturing/maintenance precedent). The router and other callers import from this package surface,
so the split into ``departments``, ``positions``, ``employees`` and ``org_chart`` is an internal
detail. Re-exported here so call sites use one import (``from app.modules.hr import service`` then
``service.create_employee(...)``).
"""

from app.modules.hr.service.departments import (
    create_department,
    get_department,
    list_departments,
    update_department,
)
from app.modules.hr.service.employees import (
    create_employee,
    get_employee,
    list_employees,
    set_compensation,
    update_employee,
)
from app.modules.hr.service.leave import (
    approve_leave_request,
    cancel_leave_request,
    create_leave_request,
    get_leave_request,
    list_leave_requests,
    reject_leave_request,
    submit_leave_request,
    update_leave_request,
)
from app.modules.hr.service.leave_accrual import accrue_leave
from app.modules.hr.service.leave_config import (
    create_leave_type,
    get_leave_type,
    list_leave_balances,
    list_leave_types,
    update_leave_type,
)
from app.modules.hr.service.org_chart import org_chart
from app.modules.hr.service.positions import (
    create_position,
    get_position,
    list_positions,
    update_position,
)

__all__ = [
    "accrue_leave",
    "approve_leave_request",
    "cancel_leave_request",
    "create_department",
    "create_employee",
    "create_leave_request",
    "create_leave_type",
    "create_position",
    "get_department",
    "get_employee",
    "get_leave_request",
    "get_leave_type",
    "get_position",
    "list_departments",
    "list_employees",
    "list_leave_balances",
    "list_leave_requests",
    "list_leave_types",
    "list_positions",
    "org_chart",
    "reject_leave_request",
    "set_compensation",
    "submit_leave_request",
    "update_department",
    "update_employee",
    "update_leave_request",
    "update_leave_type",
    "update_position",
]
