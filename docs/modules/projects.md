# Projects (`backend/app/modules/projects/`)

Projects is the **eighth business module** (PLAN 11.1), the **Project-System (PS-lite)** layer,
sitting at the **top of the dependency order** (STRUCTURE §5 / **D-056**). It is the deliberately
small PS core the [parity doc](../research/s4hana-parity.md) scopes: **projects** with a **WBS-element
hierarchy as costing objects**, **time and purchases postable to a WBS**, and a **project cost
report**. Everything else PS (networks/activities, scheduling, cost planning, budgeting with
availability control, settlement, results analysis / revenue recognition, customer-project billing)
is **out of v1** — recorded in the parity doc.

The normative design lives in [docs/architecture.md](../architecture.md) (D-017 universal journal +
its project/WBS dimension, D-021 statements/CO as projections, D-029 opaque cross-module ids, D-015
money types, D-035 conditional GETs, D-014 pagination) and the **D-056** decision in
[DECISIONS.md](../../DECISIONS.md); this guide is the operator/contributor map.

## Status

**PLAN 11.1 is COMPLETE** — this closes **Phase 11 (Projects)**. Project CRUD, a WBS-element tree
(cycle-guarded), and the project cost report (actuals by WBS + approved hours + budget variance) are
all live.

| File | Concern | Key decision |
|---|---|---|
| `constants.py` | `ProjectStatus`, `WbsStatus` enums + permission keys (registered at import) + `MAX_WBS_DEPTH` | D-056, D-009 |
| `models.py` | `Project` (`ps_projects`), `WbsElement` (`ps_wbs_elements`) | D-056, D-029, D-015 |
| `schemas.py` | Create/Update/Read/Filter for both masters + the `ProjectCostReport` / `WbsCostLine` schemas | D-015 |
| `service/projects.py` | project CRUD + customer / cost-centre validation | D-029 |
| `service/wbs.py` | WBS CRUD + code-unique-within-project + the parent cycle guard | D-056 |
| `service/report.py` | `project_cost_report` — the bounded journal projection + hr hours + variance | D-056 |
| `queries.py` | `get_project`/`project_exists`, `get_wbs_element`/`wbs_element_exists`, `wbs_elements_for_project` — the only file a later module imports | STRUCTURE §5 |
| `router.py` + `wbs_router.py` | REST under `/api/v1/projects` (one surface; the WBS sub-router mounted in `router.py`) | D-009, D-014, D-035 |

Migration: `0041_projects` (two tables + indexes, **no triggers**, down_revision 0040). It does
**not** add a journal-line project dimension — `fin_journal_lines.project_id` already exists (the
universal-journal WBS dimension since D-017 / migration 0009). There is **no** `events.py` /
`handlers.py`: projects is masters + a read report and triggers no cross-module write (an empty event
file would be a dead file — STRUCTURE §8.3).

## The opaque-WBS-dimension model (the load-bearing idea)

A **WBS element's `id` is the costing object**. When work or purchases are "posted to a WBS", a
**finance journal line** (`fin_journal_lines.project_id`) or a **HR time entry**
(`hr_time_entries.project_id`) simply carries that WBS-element id as its **opaque project dimension**.

**Finance and HR do NOT validate that id against the projects module.** It stays an opaque tag so
**finance remains the bottom of the dependency order** (D-029): finance never imports projects, HR
never imports projects. **Projects posts nothing itself** — it owns the WBS masters and the report,
and the report *reads* the journal projection + the timesheet aggregate **downward**.

This is why "purchases postable to a WBS" required **no new column and no schema change**: the journal
line has carried a `project_id` dimension since D-017. The `JournalLineCreate` schema already exposes
`project_id`, and the journal service already copies it onto the persisted line, so a posting tags a
WBS the moment a caller sets that field. Likewise HR timesheets already allocate hours to an opaque
`project_id` (PLAN 10.3 / D-054).

`projects/queries.wbs_element_exists` is exposed so a **future** projects-owned posting gate (or
finance/HR validation, once the dependency direction allows) could validate a WBS dimension before a
posting tags it — but **today no one calls it**; the tag is opaque.

## The two masters

### Project (`ps_projects`)

`code` is **user-supplied** and unique per tenant (the master-data precedent — no auto-number).
`status` is `PLANNING | ACTIVE | CLOSED | CANCELLED` (informational — it does **not** gate posting,
since finance/HR never consult it). `customer_id` is an **opaque sales customer id** (nullable,
validated via `sales/queries.customer_exists` when set). `cost_center_id` is an **opaque finance
cost-centre id** (nullable, validated via `finance/queries.cost_center_exists`). `start_date` /
`end_date` bracket the project. `budget_amount` is a **simple budget figure** feeding the cost
report's project-level variance — **not** a budget-control / availability-check mechanism (no
posting-time funds check exists in v1).

### WBS element (`ps_wbs_elements`)

The node in a project's work-breakdown tree and **the costing object**. `project_id` is the
intra-module composite tenant FK to the owning project. `code` is **unique within the project** (not
per tenant) — the same code may recur under a different project (the account-group-within-chart
precedent). `parent_id` (a nullable self composite tenant FK) builds the **tree**; the service
**cycle-guards** it (`_assert_no_parent_cycle` walks the ancestor chain, bounded by `MAX_WBS_DEPTH`,
and also rejects a parent in a *different* project). `status` is `OPEN | CLOSED` (advisory in v1 — see
below). `is_billable` flags billable work. `budget_amount` is the per-WBS budget.

**`WbsStatus.CLOSED` is advisory in v1.** A WBS element can be flagged closed to further postings, but
finance/HR tag the WBS id opaquely and do **not** consult WBS status before posting (D-029 keeps
finance at the bottom — it would have to import projects to check, which is forbidden). The flag still
surfaces on the cost report so a reader sees which elements are closed; a posting-time block would
require a projects-owned posting gate (a documented later).

## The project cost report

`GET /api/v1/projects/{id}/cost-report` (permission `projects.report.read`, optional `as_of` date).
For each WBS element of the project it shows:

- **`budget`** — the element's `budget_amount`.
- **`actual_cost`** — the sum of **POSTED** journal lines tagged with that WBS-element id (the opaque
  project dimension), via the finance journal projection `costs_by_project_dimension`. CO is a
  projection of the journal (D-021), so this is derived from journal lines, never a stored total.
- **`hours`** — **approved** timesheet hours allocated to that WBS id, via
  `hr/queries.approved_hours_by_project`. Only APPROVED timesheets count (D-054); a DRAFT or
  SUBMITTED sheet contributes nothing.
- **`variance`** — `budget − actual`.

The lines **roll up** to a project total: `total_actual_cost` / `total_hours` sum the lines, and
`total_budget` is the project's own `budget_amount` when set, else the sum of the WBS budgets (so a
project that budgets at the WBS level still gets a meaningful project-level variance). `total_variance
= total_budget − total_actual_cost`. A WBS with no postings shows **zero** actual / zero hours.
`as_of` bounds the actuals cumulatively to that posting date.

**The report is a bounded projection (PERFORMANCE §6), never N+1.** It loads the project's WBS
structure **once**, then runs **one** finance projection over **all** the WBS ids and **one** hr
aggregate over **all** the WBS ids — a fixed number of queries regardless of WBS count. The per-WBS
roll-up is pure in-memory dict lookups. A regression test doubles the WBS count (2 → 4) and asserts
the query count does not grow with it.

## What was added to `finance/queries` (a sanctioned addition)

`costs_by_project_dimension(session, tenant, project_dimension_ids, *, date_to=None) -> dict[uuid,
Decimal]` — the SUM over POSTED journal lines whose `project_id` dimension is in the given ids, of
(functional debit − functional credit), grouped by that dimension, optionally bounded by `date_to`.
It returns only the ids that actually have postings (the caller defaults the rest to zero). This is a
**sanctioned finance/queries addition** (STRUCTURE §5 / D-056): finance owns the journal projection,
and projects reads it downward by the opaque dimension — finance never imports projects, so finance
stays at the bottom. It mirrors the existing `cost_center_balance` projection exactly.

A companion `hr/queries.approved_hours_by_project(...)` (the set-based form of the existing
`approved_hours_for_project`) returns approved hours grouped by project dimension for a set of ids, so
the report's hours are one query, not one per WBS.

## Permissions (D-009)

| Key | Guards |
|---|---|
| `projects.project.read` | read / list projects |
| `projects.project.manage` | create / edit projects |
| `projects.wbs.read` | read / list WBS elements |
| `projects.wbs.manage` | create / edit WBS elements |
| `projects.report.read` | read the project cost report |

## Cross-module boundary (STRUCTURE §5)

Projects sits at the **top** of the dependency order and reads **downward** only:

- `finance/queries` — `cost_center_exists` (a project's cost centre), `costs_by_project_dimension`
  (the journal-projection actuals by WBS id).
- `hr/queries` — `approved_hours_by_project` (approved hours by WBS id).
- `sales/queries` — `customer_exists` (a project's customer).

No cycle: finance / hr / sales are older modules and import nothing from projects, so
projects→{finance,hr,sales}/queries is one-directional (STRUCTURE §5 bans only bidirectional query
imports). `projects/queries.py` is the only file a later module would import.

## What's out of scope (parity)

Per [s4hana-parity §PS](../research/s4hana-parity.md#project-system-ps): networks/activities,
scheduling/milestones, cost planning (plan vs actual), budgeting with availability control,
settlement, results analysis / event-based revenue recognition, and customer-project billing are all
deferred. v1 is WBS-only cost collection + a report over actuals (no plan or commitment columns).
