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

**PLAN 10.1 is COMPLETE** — this opens Phase 10 (Human Resources). Department/position/employee CRUD,
the masked compensation/PII read with a dedicated compensation-write endpoint, the department
hierarchy + employee org-chart reporting line with cycle guards, and an org-chart endpoint are all
live.

| File | Concern | Key decision |
|---|---|---|
| `constants.py` | `EmploymentStatus`, `EmploymentType` enums + permission keys (registered at import), incl. the sensitive `hr.employee.read_compensation` | D-052, D-009 |
| `models.py` | `Department` (`hr_departments`), `Position` (`hr_positions`), `Employee` (`hr_employees`) | D-029, D-015, D-009 |
| `schemas.py` | Create/Update/Read/Filter for the three entities + `EmployeeCompensationUpdate` + the org-chart response; **`EmployeeRead` carries the `Masked(...)` fields** | D-009, D-015 |
| `service/departments.py` | department CRUD + cost-centre/manager validation + the **hierarchy cycle guard** | D-029, D-052 |
| `service/positions.py` | position CRUD + department validation | D-052 |
| `service/employees.py` | employee CRUD + reference validation + the **manager-cycle guard** + `set_compensation` (the dedicated masked-write path) | D-009, D-052 |
| `service/org_chart.py` | the bounded recursive org-chart build | D-052 |
| `queries.py` | `get_employee`/`employee_exists`, `get_department`/`department_employees`, `employee_manager_chain`, `org_chart_for` — the only file a later module imports | STRUCTURE §5 |
| `router.py` + `position_router.py` + `employee_router.py` | REST under `/api/v1/hr` (one surface; sub-routers mounted in `router.py`) | D-009, D-014, D-035 |

Migration: `0037_hr` (three tables + indexes, no triggers, down_revision 0036). There is **no**
`events.py` / `handlers.py`: HR publishes/subscribes to no cross-module event in v1 (an empty event
file would be a dead file — STRUCTURE §8.3); payroll (10.4) will post a journal through the bus.

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
`hr.department.read` / `.manage`; `hr.position.read` / `.manage`. Registered into the code-owned
catalog at import.

## Cross-module boundary (STRUCTURE §5)

The only downward read is `finance/queries.cost_center_exists` (a department's optional cost centre)
plus a core `core_users` probe for an employee's optional login. Finance is an older module and imports
nothing from HR, so the import is one-directional (no cycle). `queries.py` is the only file a later
module (payroll, projects) imports.

## What's out of scope (parity)

Date-effective history and formal hire/transfer/terminate actions, leave/absence, timesheet/CATS,
jurisdiction-compliant payroll, pay-grade structures and comp-review cycles, talent (recruiting/
onboarding/learning/performance/succession), benefits administration, and ESS/MSS screens. See the
[parity doc HCM section](../research/s4hana-parity.md) for the full reconciliation and the "later"
notes.
