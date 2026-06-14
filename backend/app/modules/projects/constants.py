"""Projects (PS-lite) constants (STRUCTURE §3): the project / WBS enums + permission keys + the
WBS-hierarchy depth bound, registered into the core RBAC catalog at import (D-009).

A SINGLE file (STRUCTURE §8.4: split into a constants/ package only at the 400-line cap) — PLAN
11.1's WBS-cost-collector core sits well under that.

IDENTITY + NUMBERING (D-056). Both ``Project`` and ``WbsElement`` are MASTERS keyed by a
USER-SUPPLIED ``code`` — the work-centre / equipment master precedent — NOT a gapless document
number (a project/WBS is reference data a posting tags, not a posted document). The ``Project`` code
is UNIQUE per tenant; the ``WbsElement`` code is UNIQUE per (tenant, PROJECT) — a WBS code only has
to be unique within its project, so the same code may appear under different projects (the
account-group-within-chart precedent). Neither registers a core_documents entry — they are masters,
not docflow documents.

THE WBS ELEMENT IS THE COSTING OBJECT (D-056, D-017/D-029). A WBS element's ``id`` is the OPAQUE
project dimension a finance journal line (``fin_journal_lines.project_id``) and a HR time entry
(``hr_time_entries.project_id``) tag when work / purchases are "posted to a WBS". Finance and HR do
NOT validate that id against this module — it stays an opaque tag so finance remains the bottom of
the dependency order (D-029). Projects OWNS the WBS masters + the cost report; the cost report is a
PROJECTION over journal lines by that opaque dimension (finance/queries) plus approved timesheet
hours (hr/queries) — projects posts NOTHING itself.

SCOPE (s4hana-parity §PS, D-056). v1 is projects + a WBS hierarchy as cost collectors + a project
cost report (actuals by WBS + hours + a simple budget-vs-actual). Networks/activities, scheduling,
cost planning, budgeting with availability control, settlement, results analysis / revenue
recognition, and customer-project billing are explicitly OUT of v1 (recorded in the parity doc).
``budget_amount`` is a SIMPLE figure feeding the cost report's variance column — NOT a
budget-control / availability-check mechanism (no posting-time funds check exists in v1, D-056).
"""

from enum import StrEnum

from app.core.rbac import register_permissions

# The WBS tree is walked with an explicit bound so a malformed parent chain (should be impossible
# given the service cycle guard) cannot spin forever — the department/equipment-hierarchy precedent
# (D-052). A practical project breakdown is a handful of levels deep; 64 is generous headroom.
MAX_WBS_DEPTH = 64


class ProjectStatus(StrEnum):
    """Lifecycle of a PROJECT (PLAN 11.1, D-056). The service owns every transition (CLAUDE.md
    rule 7); v1 keeps the lifecycle informational — it does NOT gate posting (finance/HR tag a WBS
    id opaquely and never consult project status, D-029).

    - **PLANNING** — being set up (WBS being authored). The default at creation.
    - **ACTIVE** — in execution; the project the cost report is most often run against.
    - **CLOSED** — completed; kept for historical cost reporting. Terminal.
    - **CANCELLED** — abandoned. Terminal.
    """

    PLANNING = "PLANNING"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class WbsStatus(StrEnum):
    """Lifecycle of a WBS ELEMENT (PLAN 11.1, D-056). v1 keeps this SIMPLE: a WBS element is OPEN or
    CLOSED, an informational flag on the masters.

    - **OPEN** — the costing object accepts further postings (the default at creation).
    - **CLOSED** — closed to FURTHER postings. v1 records this as a flag ONLY: finance/HR tag the
      WBS id opaquely and do NOT consult WBS status before posting (D-029 keeps finance at the
      bottom — it would need to import projects to check, which is forbidden). The closed flag is
      therefore advisory in v1; a posting-time block would require a projects-owned posting gate,
      a documented later (D-056). It still surfaces on the cost report so a reader sees which
      elements are closed.
    """

    OPEN = "OPEN"
    CLOSED = "CLOSED"


# --- Permissions (D-009): one key per guarded endpoint action -----------------
# Project + WBS masters split read/manage (the master-data precedent); the cost REPORT gets its own
# read key so a controller can be granted the report without WBS-edit rights (segregation of duties:
# reading project cost is distinct from authoring the structure).
PROJECTS_PROJECT_READ = "projects.project.read"
PROJECTS_PROJECT_MANAGE = "projects.project.manage"
PROJECTS_WBS_READ = "projects.wbs.read"
PROJECTS_WBS_MANAGE = "projects.wbs.manage"
PROJECTS_REPORT_READ = "projects.report.read"

register_permissions(
    PROJECTS_PROJECT_READ,
    PROJECTS_PROJECT_MANAGE,
    PROJECTS_WBS_READ,
    PROJECTS_WBS_MANAGE,
    PROJECTS_REPORT_READ,
    descriptions={
        PROJECTS_PROJECT_READ: "Read projects",
        PROJECTS_PROJECT_MANAGE: "Create and edit projects",
        PROJECTS_WBS_READ: "Read WBS elements",
        PROJECTS_WBS_MANAGE: "Create and edit WBS elements",
        PROJECTS_REPORT_READ: "Read the project cost report",
    },
)
