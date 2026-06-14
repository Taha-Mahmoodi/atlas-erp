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


class LeaveRequestStatus(StrEnum):
    """Lifecycle of a LEAVE REQUEST (PLAN 10.2, D-053). The procurement requisition
    submit→approve→reject precedent (D-040), without a value-threshold rule — every request awaits
    a distinct ``hr.leave.approve`` holder.

    - **DRAFT** — created, editable, not yet routed for approval. The default at creation.
    - **SUBMITTED** — filed for approval; awaits an approver. Editing is closed.
    - **APPROVED** — approved; the employee's leave balance for the type is DECREMENTED by the
      request days at this transition (the value-bearing step, D-053).
    - **REJECTED** — declined. Terminal; no balance effect.
    - **CANCELLED** — withdrawn. From DRAFT/SUBMITTED there is no balance effect; cancelling an
      APPROVED request RESTORES the decremented balance (D-053).
    """

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class LeaveUnit(StrEnum):
    """The unit a leave type / request tracks in (PLAN 10.2, D-053). v1 tracks leave in **DAYS**
    only. Half-day granularity is expressible WITHOUT a new unit — ``days`` is a ``QuantityType``
    (NUMERIC scale 6, D-015), so a caller supplies ``0.5`` for a half day; a dedicated HALF_DAY unit
    (and shift-aware part-day math) is the documented later. The enum exists so the later unit set
    has a home and the column reads self-documenting."""

    DAYS = "DAYS"


class AccrualFrequency(StrEnum):
    """How a leave type ACCRUES (PLAN 10.2, D-053): the cadence the accrual run grants
    ``accrual_amount`` on.

    - **MONTHLY** — accrues each month (e.g. 1.67 days/month ≈ 20/year).
    - **ANNUAL** — accrues once per year (e.g. 20 days/year granted in one run).

    The accrual run is invoked per frequency (``POST /leave-balances/accrue?frequency=``) so a
    tenant runs the monthly grant monthly and the annual grant yearly, each idempotent for its
    period (D-053).
    """

    MONTHLY = "MONTHLY"
    ANNUAL = "ANNUAL"


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

# Leave (PLAN 10.2, D-053). Leave TYPES are configuration (read/manage). A leave REQUEST splits the
# filing authority (``.request`` — an employee/manager files + submits + cancels their request) from
# the distinct APPROVAL authority (``.approve`` — the value-bearing decision that decrements the
# balance; the procurement requisition .approve precedent, D-040). The accrual RUN is gated by
# ``.manage`` on the leave type (running the grant is a configuration-owner action, no
# separate key —
# the maintenance .run precedent applies to time-based generation, but accrual is set-based over the
# type config, so the type-manage key suffices).
HR_LEAVE_TYPE_READ = "hr.leave_type.read"
HR_LEAVE_TYPE_MANAGE = "hr.leave_type.manage"
HR_LEAVE_READ = "hr.leave.read"
HR_LEAVE_REQUEST = "hr.leave.request"
HR_LEAVE_APPROVE = "hr.leave.approve"

register_permissions(
    HR_EMPLOYEE_READ,
    HR_EMPLOYEE_MANAGE,
    HR_EMPLOYEE_READ_COMPENSATION,
    HR_DEPARTMENT_READ,
    HR_DEPARTMENT_MANAGE,
    HR_POSITION_READ,
    HR_POSITION_MANAGE,
    HR_LEAVE_TYPE_READ,
    HR_LEAVE_TYPE_MANAGE,
    HR_LEAVE_READ,
    HR_LEAVE_REQUEST,
    HR_LEAVE_APPROVE,
    descriptions={
        HR_EMPLOYEE_READ: "Read employees (compensation/PII masked)",
        HR_EMPLOYEE_MANAGE: "Create and edit employees (non-compensation fields)",
        HR_EMPLOYEE_READ_COMPENSATION: "View and set employee compensation and PII",
        HR_DEPARTMENT_READ: "Read departments",
        HR_DEPARTMENT_MANAGE: "Create and edit departments",
        HR_POSITION_READ: "Read positions",
        HR_POSITION_MANAGE: "Create and edit positions",
        HR_LEAVE_TYPE_READ: "Read leave types",
        HR_LEAVE_TYPE_MANAGE: "Create and edit leave types and run leave accrual",
        HR_LEAVE_READ: "Read leave requests and balances",
        HR_LEAVE_REQUEST: "File, submit and cancel leave requests",
        HR_LEAVE_APPROVE: "Approve or reject leave requests",
    },
)

# The leave-request number sequence (PLAN 10.2, D-053). Leave requests claim a gapless
# ``LV-`` number
# AT CREATION (the procurement-requisition claim-at-create precedent, D-040) so a request is
# traceable by a human-readable id from the moment it is filed — they are NOT docflow documents (no
# DocumentMixin/predecessor links: a leave request has no successor document in v1), so the
# number is
# a plain ``request_number`` column, not a core_documents registration. ``year_reset`` keeps the
# counter per calendar year (LV-2026-00001 style numbering via the sequence's year column).
LEAVE_REQUEST_SEQUENCE_NAME = "hr.leave_request"
LEAVE_REQUEST_NUMBER_PREFIX = "LV"
LEAVE_REQUEST_NUMBER_PADDING = 5

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
