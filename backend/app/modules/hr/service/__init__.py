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
from app.modules.hr.service.time_allocation import (
    hours_by_cost_center,
    hours_by_project,
)
from app.modules.hr.service.time_reads import (
    list_time_entries,
    list_timesheets,
)
from app.modules.hr.service.timesheet_lifecycle import (
    approve_timesheet,
    cancel_timesheet,
    reject_timesheet,
    submit_timesheet,
)
from app.modules.hr.service.timesheets import (
    add_time_entry,
    create_timesheet,
    get_time_entry,
    get_timesheet,
    remove_time_entry,
    update_time_entry,
    update_timesheet,
)

__all__ = [
    "accrue_leave",
    "add_time_entry",
    "approve_leave_request",
    "approve_timesheet",
    "cancel_leave_request",
    "cancel_timesheet",
    "create_department",
    "create_employee",
    "create_leave_request",
    "create_leave_type",
    "create_position",
    "create_timesheet",
    "get_department",
    "get_employee",
    "get_leave_request",
    "get_leave_type",
    "get_position",
    "get_time_entry",
    "get_timesheet",
    "hours_by_cost_center",
    "hours_by_project",
    "list_departments",
    "list_employees",
    "list_leave_balances",
    "list_leave_requests",
    "list_leave_types",
    "list_positions",
    "list_time_entries",
    "list_timesheets",
    "org_chart",
    "reject_leave_request",
    "reject_timesheet",
    "remove_time_entry",
    "set_compensation",
    "submit_leave_request",
    "submit_timesheet",
    "update_department",
    "update_employee",
    "update_leave_request",
    "update_leave_type",
    "update_position",
    "update_time_entry",
    "update_timesheet",
]
