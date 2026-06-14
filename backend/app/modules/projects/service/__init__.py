"""Projects service package (STRUCTURE §3: one file per aggregate, each <400 lines — the
maintenance/manufacturing precedent). The router and other callers import from this package surface,
so the split into ``projects`` (the project master), ``wbs`` (the WBS tree) and ``report`` (the cost
report) is an internal detail. Re-exported here so call sites use one import (``from
app.modules.projects import service`` then ``service.create_project(...)``).
"""

from app.modules.projects.service.projects import (
    create_project,
    get_project,
    list_projects,
    update_project,
)
from app.modules.projects.service.report import project_cost_report
from app.modules.projects.service.wbs import (
    create_wbs_element,
    get_wbs_element,
    list_wbs_elements,
    update_wbs_element,
)

__all__ = [
    "create_project",
    "create_wbs_element",
    "get_project",
    "get_wbs_element",
    "list_projects",
    "list_wbs_elements",
    "project_cost_report",
    "update_project",
    "update_wbs_element",
]
