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
from app.modules.hr.service.org_chart import org_chart
from app.modules.hr.service.positions import (
    create_position,
    get_position,
    list_positions,
    update_position,
)

__all__ = [
    "create_department",
    "create_employee",
    "create_position",
    "get_department",
    "get_employee",
    "get_position",
    "list_departments",
    "list_employees",
    "list_positions",
    "org_chart",
    "set_compensation",
    "update_department",
    "update_employee",
    "update_position",
]
