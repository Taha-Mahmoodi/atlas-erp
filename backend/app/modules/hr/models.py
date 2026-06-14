"""HR models (PLAN 10.1, parity HCM core = employees + departments + positions + org chart): the
``Department``, ``Position`` and ``Employee`` masters.

THREE tables, one concern (HCM v1) — well under the 400-line cap, so a single models.py (the quality
precedent; split into a models/ package only at the cap).

All three are MASTERS keyed by a USER-SUPPLIED ``code`` unique per tenant (the item-code / work-
centre precedent — no gapless document number, no DocumentMixin: HR masters are not posted documents
in the D-012 sense).

THE DEPARTMENT↔MANAGER CIRCULAR REFERENCE (D-052). A department has a manager EMPLOYEE; an employee
belongs to a department — a hard composite FK each way would be a circular table dependency the
migration could not order. Resolution: ``Department.manager_employee_id`` is a PLAIN nullable
``sa.Uuid`` (opaque, validated in the service against ``hr_employees``), NOT a composite FK; the
employee→department side IS a real composite FK. So the dependency is one-directional at the DDL
level (employee → department), and the manager link is a service-validated soft reference. The
EMPLOYEE's org-chart reporting line (``manager_id``) and the DEPARTMENT hierarchy (``parent_id``)
are intra-table SELF composite FKs (a child can never point at a parent of another tenant); the
service
guards both against cycles with a bounded walk-up.

CROSS-MODULE / SOFT IDS ARE OPAQUE (D-029/§5). ``Department.cost_center_id`` is an OPAQUE finance
cost-centre id (nullable, validated via finance/queries when set — never a cross-module FK).
``Employee.user_id`` is an OPAQUE core users id (nullable, validated via a core user probe when
set — an employee MAY also be a system user; never a hard FK from a module table to core_users).

THE MASKED FIELDS (D-009/D-052) live on ``Employee`` as ordinary columns — ``base_salary``
(MoneyType), ``currency_code``, ``national_id``, ``tax_id``, ``date_of_birth``, ``bank_account``.
The
masking is a READ-side concern of the schema layer (the ``Masked`` serializer), not the model; the
columns store the real values. They are excluded from the audit diff (D-010) — compensation/PII is
captured in v1 only through the same masking machinery in the audit viewer (a documented later); for
now ``__audit_exclude__`` keeps the raw values out of the diff rows entirely, matching the
password_hash precedent on User.
"""

import uuid
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import (
    AuditMixin,
    Base,
    TenantMixin,
    TimestampMixin,
    UuidPKMixin,
    tenant_fk,
    tenant_unique,
)
from app.core.money import MoneyType
from app.modules.hr.constants import EmploymentStatus, EmploymentType


class Department(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """An organizational DEPARTMENT (D-052): a unit employees and positions belong to.

    ``code`` is USER-SUPPLIED and unique per tenant. ``parent_id`` (nullable) is the self composite
    tenant FK forming the department HIERARCHY (a sub-department's parent); the service guards it
    against cycles. ``cost_center_id`` is an OPAQUE finance cost-centre id (nullable, validated via
    finance/queries when set — D-029, no cross-module FK) for labour-cost attribution.
    ``manager_employee_id`` is the department's manager EMPLOYEE — a PLAIN nullable ``sa.Uuid``
    (opaque, validated in the service against ``hr_employees``), NOT a composite FK, to break the
    department↔employee circular table dependency (D-052; see module docstring). ``is_active`` flags
    a retired department. Audited (D-010): master data driving the org structure.
    """

    __tablename__ = "hr_departments"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "code", name="uq_hr_departments_tenant_id_code"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        # Self composite tenant FK for the department hierarchy (a child's parent is in the same
        # tenant). Explicit name (the auto-convention would render the same; spelled for clarity).
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_id"],
            ["hr_departments.tenant_id", "hr_departments.id"],
            name="fk_hr_departments_parent_id_hr_departments",
        ),
        # The list filters on (tenant, is_active) and parent lookups walk (tenant, parent_id)
        # (PERFORMANCE §1).
        sa.Index("ix_hr_departments_tenant_id_parent_id", "tenant_id", "parent_id"),
    )

    code: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    # Self composite tenant FK (the department hierarchy parent).
    parent_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    # Opaque finance cost-centre id (D-029): no cross-module FK; the service validates it via
    # finance/queries when set. For labour-cost attribution.
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    # The manager employee — a PLAIN opaque uuid (NOT a composite FK) to break the
    # department↔employee circular dependency (D-052); the service validates it against
    # hr_employees.
    manager_employee_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )


class Position(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A job POSITION (D-052): a role title within a department employees can hold.

    ``code`` is USER-SUPPLIED and unique per tenant. ``title`` is the role title. ``department_id``
    (nullable) is the composite tenant FK to the owning department. ``is_active`` flags a retired
    position. Audited (D-010): master data driving the org structure.
    """

    __tablename__ = "hr_positions"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "code", name="uq_hr_positions_tenant_id_code"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("hr_departments", "department_id"),
        sa.Index("ix_hr_positions_tenant_id_department_id", "tenant_id", "department_id"),
    )

    code: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    title: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    # Composite tenant FK to hr_departments (nullable — a position may be unassigned).
    department_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )


class Employee(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """An EMPLOYEE (D-052): a person employed by the tenant, optionally a system user.

    ``employee_code`` is USER-SUPPLIED and unique per tenant. ``department_id`` / ``position_id``
    are nullable composite tenant FKs. ``manager_id`` is the self composite tenant FK forming the
    org-chart reporting line (the employee this one reports to); the service guards it against
    cycles.
    ``user_id`` is an OPAQUE core users id (nullable, validated via a core user probe when set — the
    optional link to a login account; never a hard FK to core_users). ``employment_status`` /
    ``employment_type`` run their enums; ``hire_date`` / ``termination_date`` (nullable) bracket the
    engagement.

    THE MASKED FIELDS (D-009/D-052): ``base_salary`` (MoneyType) + ``currency_code`` are the
    compensation; ``national_id`` / ``tax_id`` / ``date_of_birth`` / ``bank_account`` are the PII.
    They store the REAL values; the read-side masking is the schema layer's concern (the ``Masked``
    serializer behind ``hr.employee.read_compensation``). Audited (D-010), but these sensitive
    columns are in ``__audit_exclude__`` so the raw values never land in an audit diff (the
    password_hash precedent on User).
    """

    __tablename__ = "hr_employees"
    # D-010: keep compensation/PII out of every audit diff (insert, update, delete). The audit
    # viewer
    # masking these with the same Masked machinery is a documented later (D-052); for v1 they are
    # excluded outright so raw pay/PII is never written to core_audit_log.
    __audit_exclude__ = frozenset(
        {"base_salary", "national_id", "tax_id", "date_of_birth", "bank_account"}
    )
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "employee_code", name="uq_hr_employees_tenant_id_employee_code"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("hr_departments", "department_id"),
        tenant_fk("hr_positions", "position_id"),
        # Self composite tenant FK for the org-chart reporting line (a report's manager is in the
        # same tenant).
        sa.ForeignKeyConstraint(
            ["tenant_id", "manager_id"],
            ["hr_employees.tenant_id", "hr_employees.id"],
            name="fk_hr_employees_manager_id_hr_employees",
        ),
        # The list filters on (tenant, department, status); the manager chain and org-chart build
        # walk (tenant, manager_id) (PERFORMANCE §1).
        sa.Index(
            "ix_hr_employees_tenant_id_department_id_status",
            "tenant_id",
            "department_id",
            "status",
        ),
        sa.Index("ix_hr_employees_tenant_id_manager_id", "tenant_id", "manager_id"),
    )

    employee_code: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    first_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(sa.String(320), nullable=True)
    # Nullable composite tenant FKs.
    department_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    position_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    # Self composite tenant FK (the org-chart reporting manager).
    manager_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    # Opaque core users id (D-029): no hard FK; the service validates it via a core user probe when
    # set. The optional link to a login account (an employee MAY also be a system user).
    user_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=EmploymentStatus.ACTIVE.value,
        server_default="ACTIVE",
    )
    employment_type: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=EmploymentType.FULL_TIME.value,
        server_default="FULL_TIME",
    )
    hire_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    termination_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)

    # --- Masked compensation + PII (D-009/D-052): real values stored; read-masked in the schema ---
    base_salary: Mapped[Decimal | None] = mapped_column(MoneyType(), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(sa.String(3), nullable=True)
    national_id: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    bank_account: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
