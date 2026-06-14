"""HR constants (STRUCTURE §3): the employee enums + permission keys, registered into the core RBAC
catalog at import (D-009).

A SINGLE file (STRUCTURE §8.4: split into a constants/ package only at the 400-line cap) — PLAN
10.1's small HCM core sits well under that.

IDENTITY + NUMBERING (D-052). All three entities are MASTERS keyed by a USER-SUPPLIED ``code``
unique per tenant (the item-code / work-centre master precedent): ``employee_code`` on the employee,
``code`` on the department and position. None claims a gapless document number — HR masters are not
posted documents in the D-012 sense (no docflow), unlike a maintenance order.

THE SENSITIVE PERMISSION (D-009/D-052). ``hr.employee.read_compensation`` is the key the ``Masked``
serializer checks at serialization time: a viewer holding it sees the employee's compensation/PII
(salary, national/tax id, date of birth, bank account); a viewer without it sees those fields as
``None``. It is ALSO the gate on the dedicated compensation-WRITE endpoint (the masked fields are
excluded from the general Update; see ``schemas.py`` / ``router.py``). So a user may hold
``hr.employee.manage`` (edit name/department/etc.) yet NOT ``hr.employee.read_compensation`` — that
user manages employees but can neither see nor set their pay.

SCOPE (s4hana-parity §HCM, D-052). v1 is employees + departments + positions + org chart. No
date-effective history, no formal hire/transfer/terminate actions, no leave, no timesheet, no real
payroll, no talent/recruiting/benefits.
"""

from enum import StrEnum

from app.core.rbac import register_permissions


class EmploymentStatus(StrEnum):
    """Lifecycle status of an EMPLOYEE (PLAN 10.1, D-052).

    - **ACTIVE** — currently employed. The default at creation.
    - **ON_LEAVE** — temporarily away (parental, sabbatical, long absence) but still employed.
    - **TERMINATED** — employment ended. Terminal; ``termination_date`` is set. v1 has no formal
      terminate ACTION (date-effective actions are out of scope, D-052) — the status is set via the
      ordinary update path.
    """

    ACTIVE = "ACTIVE"
    ON_LEAVE = "ON_LEAVE"
    TERMINATED = "TERMINATED"


class EmploymentType(StrEnum):
    """The employment ARRANGEMENT of an employee (PLAN 10.1, D-052).

    - **FULL_TIME** — a permanent full-time employee. The default at creation.
    - **PART_TIME** — a permanent part-time employee.
    - **CONTRACT** — a fixed-term / contractor engagement.
    """

    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    CONTRACT = "CONTRACT"


# --- Permissions (D-009): one key per guarded endpoint action -----------------
# Employee + department + position masters each split read/manage. The employee adds the SENSITIVE
# read_compensation key (D-052): it gates BOTH the masked compensation/PII fields' visibility (the
# Masked serializer checks it) AND the dedicated compensation-write endpoint. A holder of
# hr.employee.manage can edit an employee's non-sensitive fields but, without read_compensation, can
# neither see nor write pay.
HR_EMPLOYEE_READ = "hr.employee.read"
HR_EMPLOYEE_MANAGE = "hr.employee.manage"
HR_EMPLOYEE_READ_COMPENSATION = "hr.employee.read_compensation"
HR_DEPARTMENT_READ = "hr.department.read"
HR_DEPARTMENT_MANAGE = "hr.department.manage"
HR_POSITION_READ = "hr.position.read"
HR_POSITION_MANAGE = "hr.position.manage"

register_permissions(
    HR_EMPLOYEE_READ,
    HR_EMPLOYEE_MANAGE,
    HR_EMPLOYEE_READ_COMPENSATION,
    HR_DEPARTMENT_READ,
    HR_DEPARTMENT_MANAGE,
    HR_POSITION_READ,
    HR_POSITION_MANAGE,
    descriptions={
        HR_EMPLOYEE_READ: "Read employees (compensation/PII masked)",
        HR_EMPLOYEE_MANAGE: "Create and edit employees (non-compensation fields)",
        HR_EMPLOYEE_READ_COMPENSATION: "View and set employee compensation and PII",
        HR_DEPARTMENT_READ: "Read departments",
        HR_DEPARTMENT_MANAGE: "Create and edit departments",
        HR_POSITION_READ: "Read positions",
        HR_POSITION_MANAGE: "Create and edit positions",
    },
)

# The default currency code stamped on a new employee's compensation when none is supplied. A plain
# ISO 4217 alpha-3 (not validated against finance currencies in v1 — compensation currency is
# descriptive metadata on the masked record, not a posting amount; payroll in 10.4 will validate it
# when it posts a journal).
DEFAULT_COMPENSATION_CURRENCY = "USD"

# Depth cap for the hierarchy/cycle-guard walk-ups (department parent chain + employee manager
# chain)
# and the org-chart recursive build (D-052). A real org is far shallower than this; the cap is a
# belt-and-braces guard so a malformed chain (should be impossible given the cycle guard) can never
# spin forever. PERFORMANCE §6: the walk is bounded, the org-chart build is a bounded recursive
# read.
MAX_HIERARCHY_DEPTH = 64
