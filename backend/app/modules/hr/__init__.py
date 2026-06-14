"""HR module (PLAN 10.1) — the EIGHTH business module (s4hana-parity §HCM).

PLAN 10.1 OPENS the Human-Capital area with the DELIBERATELY SMALL HCM core the parity doc scopes
(docs/research/s4hana-parity.md §HCM): the EMPLOYEE master (with MASKED compensation/PII),
DEPARTMENTS, POSITIONS, and the reporting ORG CHART. Talent/recruiting/benefits and a
jurisdiction-compliant real payroll are explicitly OUT of v1; leave/timesheet/payroll-lite arrive in
later 10.x plans (recorded in the parity doc and D-052).

This is the FIRST real module use of the **D-009 field-level read masking** serializer: the
employee's compensation/PII fields (``base_salary``, ``national_id``, ``tax_id``, ``date_of_birth``,
``bank_account``) are wrapped in ``Masked(tp, HR_EMPLOYEE_READ_COMPENSATION)``. A viewer WITHOUT the
``hr.employee.read_compensation`` key sees them serialized as ``None``; only the sensitive
permission
reveals the real values. Per the D-009 write-side convention, those masked fields are EXCLUDED from
the general Employee Update schema and are written only through a dedicated, permission-guarded
``PATCH /employees/{id}/compensation`` endpoint, so a partial update can never silently null
compensation.

HR sits ABOVE finance in the dependency order (STRUCTURE §5 / D-052). It:

- READS DOWNWARD (D-029) via ``finance/queries.cost_center_exists`` — a department's optional cost
  centre for labour-cost attribution — never finance models, never a cross-module FK.
- Links an employee to an OPAQUE core ``user_id`` (the login account; validated via a core user
  probe when set, never a hard FK from a module table to ``core_users``). An EMPLOYEE is a person
  who
  MAY also be a system user; not every employee has a login, and not every user is an employee.
- Publishes/subscribes to NO cross-module event in v1 (HR masters drive no cross-module effect;
  payroll in 10.4 will post a journal through the bus). So there is NO events.py / handlers.py here
  (an empty event file would be a dead file — STRUCTURE §8.3).

The DEPARTMENT↔MANAGER circular reference (a department has a manager employee; an employee belongs
to a department) is resolved by making ``Department.manager_employee_id`` a PLAIN nullable
``sa.Uuid`` (opaque, validated in the service against ``hr_employees``) — NOT a hard composite FK —
so there is no circular composite-FK dependency between the two tables (D-052). The org-chart
reporting line (``Employee.manager_id``) and the department hierarchy (``Department.parent_id``) ARE
intra-table self composite FKs; the service guards both against cycles with a bounded walk-up.

No cycle (D-052): finance is an OLDER module and imports nothing from hr, so hr→finance/queries is
one-directional (STRUCTURE §5 bans only bidirectional query imports). ``hr/queries.py`` is the only
file a later module (payroll, projects) would import.
"""
