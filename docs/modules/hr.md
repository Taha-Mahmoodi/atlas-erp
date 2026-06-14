# HR (`backend/app/modules/hr/`)

HR is the **eighth business module** (PLAN 10.1), the **Human-Capital (HCM)** core, sitting **above
finance** in the dependency order (STRUCTURE §5 / **D-052**). It is the deliberately small HCM core
the [parity doc](../research/s4hana-parity.md) scopes: the **employee master** (with **masked**
compensation/PII), **departments**, **positions**, and the reporting **org chart**. Talent,
recruiting, benefits, leave, timesheet and a jurisdiction-compliant real payroll are **out of v1**
(leave/time/payroll-lite arrive in later 10.x plans; talent/benefits stay out — recorded in the
parity doc).

This module is the **first real use of the D-009 field-level read-masking serializer**: an employee's
compensation/PII fields are wrapped in `Masked(tp, "hr.employee.read_compensation")` and serialize to
`None` for any viewer who does not hold that permission.

The normative design lives in [docs/architecture.md](../architecture.md) (**D-009** RBAC + field
masking, D-029 opaque cross-module ids, D-015 money types, D-014 pagination/envelope, D-035
conditional GETs) and the **D-052** decision in [DECISIONS.md](../../DECISIONS.md); this guide is the
operator/contributor map.

## Status

**PLAN 10.1, 10.2 and 10.3 are COMPLETE** — this opens Phase 10 (Human Resources). 10.1: department/
position/employee CRUD, the masked compensation/PII read with a dedicated compensation-write
endpoint, the department hierarchy + employee org-chart reporting line with cycle guards, and an
org-chart endpoint. 10.2: leave types with periodic accrual, a per-employee-per-type running balance,
and the leave-request approval flow (see [Leave](#leave-plan-102--d-053) below). 10.3: timesheets +
time entries with project & cost-centre allocation, header-level approval, and the allocation reports
(see [Time tracking](#time-tracking-plan-103--d-054) below).

| File | Concern | Key decision |
|---|---|---|
| `constants.py` | `EmploymentStatus`, `EmploymentType`, `LeaveRequestStatus`, `LeaveUnit`, `AccrualFrequency`, `TimesheetStatus` enums + permission keys (registered at import), incl. the sensitive `hr.employee.read_compensation` + the `LV-`/`TS-` sequences | D-052, D-053, D-054, D-009 |
| `models/org.py` | `Department` (`hr_departments`), `Position` (`hr_positions`), `Employee` (`hr_employees`) | D-029, D-015, D-009 |
| `models/leave.py` | `LeaveType` (`hr_leave_types`), `LeaveBalance` (`hr_leave_balances`), `LeaveRequest` (`hr_leave_requests`) | D-053, D-015 |
| `models/time.py` | `Timesheet` (`hr_timesheets`), `TimeEntry` (`hr_time_entries`) | D-054, D-015, D-029 |
| `schemas.py` / `time_schemas.py` | Create/Update/Read/Filter for all entities + `EmployeeCompensationUpdate` + the org-chart response + the leave/timesheet action payloads + the allocation report; **`EmployeeRead` carries the `Masked(...)` fields** | D-009, D-015, D-054 |
| `service/departments.py` | department CRUD + cost-centre/manager validation + the **hierarchy cycle guard** | D-029, D-052 |
| `service/positions.py` | position CRUD + department validation | D-052 |
| `service/employees.py` | employee CRUD + reference validation + the **manager-cycle guard** + `set_compensation` (the dedicated masked-write path) | D-009, D-052 |
| `service/org_chart.py` | the bounded recursive org-chart build | D-052 |
| `service/leave_config.py` | leave-type CRUD + balance reads | D-053 |
| `service/leave.py` | the leave-request lifecycle + the **approve-decrements / cancel-restores** balance logic | D-053, D-040 |
| `service/leave_accrual.py` | the **period-keyed idempotent accrual run** | D-053 |
| `service/timesheets.py` | timesheet header CRUD + time-entry add/update/remove + the **maintained `total_hours`** + cost-centre validation / `project_id`-opaque | D-054, D-029 |
| `service/timesheet_lifecycle.py` | the timesheet submit → approve / reject / cancel transitions | D-054 |
| `service/time_reads.py` / `service/time_allocation.py` | timesheet list + entry list / the **APPROVED-only allocation aggregates** | D-054, D-014 |
| `queries.py` | the 10.1/10.2 reads + `get_timesheet`/`timesheets_for_employee`/`time_entries_for_timesheet`/`approved_hours_for_project`/`approved_hours_for_cost_center` — the only file a later module imports | STRUCTURE §5 |
| `router.py` + `position_router.py` + `employee_router.py` + `leave_router.py` + `timesheet_router.py` | REST under `/api/v1/hr` (one surface; sub-routers mounted in `router.py`) | D-009, D-014, D-035 |

Migrations: `0037_hr` (org masters), `0038_hr_leave` (leave — three tables), and `0039_hr_time`
(time — `hr_timesheets` + `hr_time_entries` + indexes, no triggers, down_revision 0038). There is
**no** `events.py` / `handlers.py`: HR publishes/subscribes to no cross-module event in v1 (an empty
event file would be a dead file — STRUCTURE §8.3); payroll (10.4) will post a journal through the bus
and may **read** leave + approved time via `queries.py`.

## Compensation masking (the headline of 10.1 — D-009)

The employee's sensitive fields are stored as ordinary columns (real values) but **read-masked** in
the schema:

| Masked field | Type | Kind |
|---|---|---|
| `base_salary` | money (Decimal) | compensation |
| `currency_code` | str | compensation |
| `national_id` | str | PII |
| `tax_id` | str | PII |
| `date_of_birth` | date | PII |
| `bank_account` | str | PII |

**The gate is `hr.employee.read_compensation`.** `EmployeeRead` declares each field as
`Masked(tp, "hr.employee.read_compensation")`. At serialization the `Masked` serializer reads the
`current_permissions` ContextVar (set per request by `get_current_user`) and emits the real value
only if the key is present, else `None`. Masking is therefore **per request, not stored**: the same
employee row serializes pay for a compensation-holder and `None` for everyone else, in the same
process, with no extra query. Name/code/department/status and the rest are always visible — masking
is field-level, not row-level. Outside a request (jobs, tests without the `permissions_context`
fixture) the ContextVar defaults to empty, so masking **fails closed**.

### The compensation-write path (D-009 write-side convention)

Because a viewer who cannot SEE compensation must not be able to null it through a partial update, the
masked fields are **excluded from `EmployeeUpdate`** entirely. They are written through exactly two
paths:

1. **`EmployeeCreate`** — initial values at creation. The `POST /employees` endpoint is guarded by
   **both** `hr.employee.manage` **and** `hr.employee.read_compensation`, so a manage-only user cannot
   seed pay.
2. **`PATCH /employees/{id}/compensation`** (`EmployeeCompensationUpdate`) — the dedicated post-create
   write path, guarded by **`hr.employee.read_compensation`**. Only the supplied fields change
   (`exclude_unset`), so salary can be updated without touching the PII.

A holder of `hr.employee.manage` but NOT `read_compensation` can edit an employee's name/department/
etc., gets masked reads, and is **403** on the compensation endpoint.

## The three entities

### Department (`hr_departments`)

A user-coded org unit (UNIQUE per tenant). `parent_id` is a self composite tenant FK forming the
**hierarchy** (cycle-guarded in the service). `cost_center_id` is an **opaque** finance cost-centre id
(D-029, validated via `finance/queries.cost_center_exists`, no cross-module FK). `manager_employee_id`
is the department's manager employee — see the circular-reference note below. `is_active` retires it.

### Position (`hr_positions`)

A user-coded job title (UNIQUE per tenant). `department_id` is a nullable composite tenant FK to the
owning department. `is_active` retires it.

### Employee (`hr_employees`)

A person (`employee_code` UNIQUE per tenant). `department_id` / `position_id` are nullable composite
tenant FKs. `manager_id` is the self composite tenant FK forming the **org-chart reporting line**
(cycle-guarded). `user_id` is an **opaque** core users id (nullable, validated via a core user probe;
an employee MAY also be a system user — never a hard FK to `core_users`). `status` / `employment_type`
run their enums; `hire_date` / `termination_date` bracket the engagement. The compensation/PII columns
are the masked set above; they are in `__audit_exclude__` so raw pay/PII never lands in an audit diff.

## The department↔manager circular reference (D-052)

A department has a manager employee; an employee belongs to a department — a hard composite FK each way
would be a circular table dependency the migration could not order. **Resolution:**
`Department.manager_employee_id` is a **plain nullable `Uuid`** (opaque, validated in the service
against `hr_employees`), NOT a composite FK; the employee→department side IS a real composite FK. So
the DDL dependency is one-directional (employee → department), and the manager link is a
service-validated soft reference. (The employee `manager_id` reporting line and the department
`parent_id` hierarchy ARE intra-table self composite FKs — those self-references are not circular.)

## The cycle guards

Both hierarchies are guarded in the service before any row is written, by walking the would-be
ancestor/reporting chain UP and rejecting a self-reference or a chain that loops back to the node being
edited (bounded by `MAX_HIERARCHY_DEPTH = 64`):

- **Department hierarchy** — `_assert_no_parent_cycle` (422 `hr.department_cycle`).
- **Employee org chart** — `_assert_no_manager_cycle` (422 `hr.manager_cycle`).

The org-chart **build** (`service/org_chart.py`) loads every employee in **one** query
(`queries.org_chart_for`, no per-node N+1 — PERFORMANCE §6) and assembles the nested tree in memory,
also bounded by the depth cap and a `visited` set as a belt-and-braces safety net. The chart carries
name/code/title only — no compensation — so any `hr.employee.read` holder may view it.

## Permissions (D-009)

`hr.employee.read` / `.manage` / **`.read_compensation`** (the sensitive gate);
`hr.department.read` / `.manage`; `hr.position.read` / `.manage`; `hr.leave_type.read` / `.manage`
(config + the accrual run); `hr.leave.read` (requests + balances); `hr.leave.request` (file/submit/
cancel) / **`.approve`** (the distinct approval authority). Registered into the code-owned catalog at
import.

## Leave (PLAN 10.2 — D-053)

Leave types with periodic accrual, a per-employee-per-type running balance, and a leave-request
approval flow. All intra-HR (no cross-module event); payroll (10.4) may **read** balances/requests
via `queries.py`. REST under `/api/v1/hr` (leave-types, leave-balances, leave-requests).

### Leave types and accrual

A **`LeaveType`** (`hr_leave_types`, user `code` unique per tenant) defines how a kind of leave
accrues: `accrual_frequency` (**MONTHLY|ANNUAL**), `accrual_amount` (days per period, a
`QuantityType` so 1.67/month is exact — D-015), an optional `max_balance` accrual cap, `is_paid`, and
`is_active`. The tracking `unit` is **DAYS** in v1; a half day is expressible as a fractional
`days = 0.5` with no new unit (a dedicated HALF_DAY unit + shift math is the documented later).
`accrual_amount >= 0` and, when a cap is set, `max_balance >= accrual_amount` (a cap below one
period's grant is a misconfiguration, rejected).

The **accrual run** `POST /leave-balances/accrue?frequency=&as_of=` (gated by `hr.leave_type.manage`;
default `as_of` today) is set-based (the maintenance preventive-generation analogue — PERFORMANCE §2):
it derives the **period key** (`YYYY-MM` for MONTHLY, `YYYY` for ANNUAL), loads the ACTIVE employees
and the ACTIVE leave types of that frequency in two queries, and grants `accrual_amount` to each
(employee × type) balance, opening a `LeaveBalance` row on first accrual.

- **Idempotency guard.** Each balance carries `last_accrual_period`. The run grants a pair only when
  its `last_accrual_period` differs from the run period, then stamps it — so a **same-period re-run
  grants nothing** (the generate-once-per-period guarantee). The endpoint is also D-013 idempotent
  (Idempotency-Key replay).
- **Cap.** When `max_balance` is set the grant is clamped so `balance_days` never exceeds the cap (0
  when already at/over, a partial grant to lift exactly to the cap). A capped balance is still
  stamped so it is not re-granted later; `accrued_to_date` records only what was actually granted.

### Balances

A **`LeaveBalance`** (`hr_leave_balances`, UNIQUE(tenant, employee, leave type)) is the running
balance: `balance_days` (available now), `accrued_to_date` and `taken_to_date` (running totals for
traceability), and `last_accrual_period` (the guard above). Read-only over the API
(`GET /employees/{id}/leave-balances`, gated by `hr.leave.read`) — written only by the accrual run
and the request approve/cancel transitions.

### The request approval flow

A **`LeaveRequest`** (`hr_leave_requests`) claims a gapless **`LV-`** `request_number` at creation
(the procurement-requisition claim-at-create precedent — D-040) but is not a docflow document (no
successor in v1). It carries `days` (caller-supplied, validated `> 0`; `start_date`/`end_date` stored
for reference with `end >= start` enforced — business-day computation from the dates is the
documented later), `status`, `reason`/`notes`, and on decision `approved_by` + `decided_at`.

Lifecycle (mirrors the procurement requisition submit→approve→reject precedent, **without** a value
threshold — every submitted request awaits an approver):

`DRAFT` (create + edit, `hr.leave.request`) → `SUBMITTED` (submit) → `APPROVED` / `REJECTED`
(`hr.leave.approve`), or `DRAFT`/`SUBMITTED`/`APPROVED` → `CANCELLED`.

- **APPROVE decrements the balance** by `days` (raising `taken_to_date`). If the available balance is
  below `days` → **422 `hr.insufficient_leave_balance`** — v1 **blocks** negative balances (an
  allow-negative leave type is the documented later); a missing balance row counts as 0 available.
- **REJECT** has no balance effect.
- **CANCEL of an APPROVED request restores the balance** (adds `days` back, lowers `taken_to_date`);
  cancelling from DRAFT/SUBMITTED has no balance effect; a terminal (REJECTED/CANCELLED) request
  cannot be cancelled.

The **`hr.leave.request` vs `hr.leave.approve` split** is the distinct-approval-authority pattern
(D-040): a `.request` holder files and submits but is 403 on approve; the value-bearing transition
(the one that moves the balance) requires `.approve`. Create/submit/approve/reject are D-013
idempotent; the leave-type list carries the D-035 conditional-GET ETag (config = reference data);
lists are paginated within the ≤3-query budget.

## Time tracking (PLAN 10.3 — D-054)

The CATS-style timesheet (s4hana-parity §HCM "Time recording with account assignment" = Full): a
**`Timesheet` header** groups an employee's time entries over a period and goes through HEADER-level
approval; **`TimeEntry` lines** hang off it, each carrying an **allocation** to a project and/or a
cost centre — the cost/project allocation deliverable.

### The timesheet + entry model

- **`Timesheet`** (`hr_timesheets`): `UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin`. It
  claims a gapless **`TS-`** `timesheet_number` at creation (the leave-request claim-at-create
  precedent, D-040/D-053) but is **NOT a docflow document** (no `DocumentMixin` — a timesheet has no
  successor document in v1). Composite tenant FK to `hr_employees`; `period_start`/`period_end`
  (Date, `end >= start`); `status` (`TimesheetStatus`: DRAFT|SUBMITTED|APPROVED|REJECTED);
  `total_hours` (a **maintained** `QuantityType` sum of the entry hours, kept in step by the service
  on every line add/update/remove); `submitted_at`/`approved_at`/`approved_by` (opaque core users
  id, no FK). UNIQUE(tenant, employee_id, period_start) — one timesheet per employee per period.
- **`TimeEntry`** (`hr_time_entries`): `UuidPKMixin, TenantMixin, TimestampMixin` (the line is not
  separately audited — the header is the audited unit, the journal-line precedent). Composite tenant
  FK to `hr_timesheets`; `entry_date` (within the header period); `hours` (`QuantityType`, CHECK
  > 0); `task_description`; `is_billable` (default false). Entries can repeat per day/project, so
  there is **no** unique constraint on the line — just an index (tenant, timesheet_id).

### `project_id` is opaque/unvalidated until Phase 11; `cost_center_id` is validated

A time entry's **`cost_center_id`** is an opaque finance cost-centre id **validated** via
`finance/queries.cost_center_exists` when set (D-029) — a bad id is a 422. A time entry's
**`project_id`** is a **nullable opaque `Uuid` stored as-is and NOT validated in v1**: the projects
module is **Phase 11 (not yet built)**, so there is no table to validate against and **no forward
dependency on projects is created**. The validation hook wires up when `projects/queries` exists in
Phase 11 — at which point `add_time_entry`/`update_time_entry` will call a projects existence probe
exactly as they call `cost_center_exists` today, and `approved_hours_for_project` (already in
`hr/queries`) is the per-project hook Phase-11 project costing will call.

### The approval flow

The header lifecycle mirrors the leave-request submit → approve / reject precedent (D-053) but
approves at the **header** level (the SAP CATS model). Lines are editable **only while the header is
a DRAFT**. **DRAFT** (create; employee exists, `end >= start`, TS- number claimed) → **SUBMITTED**
(submit; stamps `submitted_at`, lines frozen) → **APPROVED**/**REJECTED** (record approver +
decision time). A SUBMITTED timesheet can be **cancelled** = reopened to DRAFT so the filer can edit
and re-submit; an APPROVED/REJECTED timesheet is terminal. **APPROVED is the value-bearing state**:
only entries of APPROVED timesheets feed the allocation aggregates. Create/submit/approve/reject are
D-013 idempotent.

The **`hr.timesheet.manage` vs `hr.timesheet.approve` split** is the distinct-approval-authority
pattern: `.manage` creates / edits draft entries / submits / cancels; `.approve` is the distinct
approval authority (approve/reject). A `.manage` holder can submit but is 403 on approve.
`.read` reads timesheets + entries + the allocation report.

### Allocation reports

`hours_by_cost_center` / `hours_by_project` are **set-based GROUP-BY aggregates over APPROVED time
entries only** (DRAFT/SUBMITTED/REJECTED time is provisional and never costed), each one query,
optionally bounded by an entry-date range. They back `GET /timesheets/allocation?by=cost_center|
project&from=&to=` and feed **project costing in Phase 11** and **CO reporting**. The `hr/queries`
companions `approved_hours_for_project(project_id)` and `approved_hours_for_cost_center(...)` are the
per-dimension hooks a later module reads.

### Endpoints + structure

`timesheet_router.py` is mounted into `router.py` (ONE surface at `/api/v1/hr`): timesheets CRUD +
submit/approve/reject/cancel; nested `GET/POST /timesheets/{id}/time-entries` + PATCH/DELETE for a
line; the allocation report (declared before `/{id}` so the literal path wins). The timesheet schemas
live in a sibling `time_schemas.py` and the service in `service/timesheets.py` (header + entries),
`service/timesheet_lifecycle.py` (the approval transitions), `service/time_reads.py` (list +
pagination), `service/time_allocation.py` (the aggregates) — each under the 400-line cap. Lists are
paginated within the ≤3-query budget. **No cross-module events** — time is intra-HR; payroll (10.4)
and project costing (11) READ approved time via `hr/queries`.

## Cross-module boundary (STRUCTURE §5)

The only downward read is `finance/queries.cost_center_exists` (a department's optional cost centre
and a time entry's optional cost centre) plus a core `core_users` probe for an employee's optional
login. Finance is an older module and imports nothing from HR, so the import is one-directional (no
cycle). `queries.py` is the only file a later module (payroll, projects) imports — including the
`approved_hours_for_project`/`approved_hours_for_cost_center` time-allocation hooks.

## What's out of scope (parity)

Date-effective history and formal hire/transfer/terminate actions; jurisdiction-compliant payroll;
pay-grade structures and comp-review cycles; talent (recruiting/onboarding/learning/performance/
succession); benefits administration; and ESS/MSS screens. **Leave and absence management** (PLAN
10.2) and **time recording with project & cost-centre allocation** (PLAN 10.3) are now in scope.
Time-tracking "later" items: validating `project_id` once the projects module exists (Phase 11);
work-schedule rules and overtime/premium evaluation; per-entry approval; and a maintenance-expense /
labour-cost journal from approved time (payroll 10.4 + project costing 11 read approved time today).
Leave-specific "later" items — work-schedule collision checks, quota carryover rules, business-day
computation, allow-negative balances, and a HALF_DAY unit — are noted inline. See the
[parity doc HCM section](../research/s4hana-parity.md) for the full reconciliation and the "later"
notes.
