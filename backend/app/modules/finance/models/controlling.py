"""Controlling (CO) master data + allocations (PLAN 4.7).

The fifth file in the finance ``models/`` package (STRUCTURE §3). Controlling is a PROJECTION of
the universal journal (D-021): cost centres and profit centres are journal-line DIMENSIONS
(``fin_journal_lines.cost_center_id`` / ``profit_center_id``, opaque ``sa.Uuid`` validated at the
service layer per D-022), and an allocation is just one more balanced journal entry that moves cost
between cost centres on a dedicated clearing account — no separate CO ledger is stored.

Five tables:

- ``CostCenter`` (``fin_cost_centers``): a cost-collecting unit. Self-referential ``parent_id``
  builds a hierarchy; the service rejects cycles. ``default_profit_center_id`` is an optional
  composite tenant FK to a profit centre.
- ``ProfitCenter`` (``fin_profit_centers``): a margin-reporting unit; self-referential hierarchy.
- ``AllocationRule`` (``fin_allocation_rules``): names a SOURCE cost centre whose net period cost is
  redistributed; ``basis`` says how the target weights are read (PERCENT sums to 100; FIXED_WEIGHT
  is proportional).
- ``AllocationRuleTarget`` (``fin_allocation_rule_targets``): a (rule, target cost centre, weight)
  row. UNIQUE per rule+target.
- ``AllocationRun`` (``fin_allocation_runs``): bookkeeping for one execution of a rule for a period;
  DocumentMixin (registry entry + claimed number at posting) and a link to the posted journal entry.

All five follow the D-007 composite-tenant-FK backstop; enum-valued columns are plain ``sa.String``
storing the StrEnum value (the rest of finance's convention). Money columns are ``MoneyType``
(D-015). Cost-centre dimensions on the journal stay opaque ``sa.Uuid`` — fin_journal_lines is
trigger-bearing and must not gain FKs (D-022), so dimension integrity is the service's job.
"""

import uuid
from datetime import date

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.docflow import DocumentMixin, document_fk
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
from app.modules.finance.constants import AllocationBasis, AllocationRunStatus


class ProfitCenter(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A profit centre (PLAN 4.7): a margin-reporting unit a journal line can carry as the
    ``profit_center_id`` dimension. Self-referential ``parent_id`` (composite tenant FK) builds a
    hierarchy the service keeps acyclic. UNIQUE(tenant, code). Audited (D-010): master data."""

    __tablename__ = "fin_profit_centers"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "code", name="uq_fin_profit_centers_tenant_id_code"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("fin_profit_centers", "parent_id"),
    )

    code: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )


class CostCenter(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A cost centre (PLAN 4.7): a cost-collecting unit a journal line carries as the
    ``cost_center_id`` dimension, so every cost-centre report is a projection over journal lines
    (D-021). Self-referential ``parent_id`` (composite tenant FK) builds a hierarchy the service
    keeps acyclic; ``default_profit_center_id`` optionally links to a profit centre.
    UNIQUE(tenant, code). Audited (D-010): master data."""

    __tablename__ = "fin_cost_centers"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "code", name="uq_fin_cost_centers_tenant_id_code"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("fin_cost_centers", "parent_id"),
        tenant_fk("fin_profit_centers", "default_profit_center_id"),
    )

    code: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    manager_name: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    default_profit_center_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)


class AllocationRule(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """An allocation rule (PLAN 4.7): names the SOURCE cost centre whose net period cost is
    redistributed to its targets. ``basis`` (PERCENT | FIXED_WEIGHT) says how target weights read.
    Composite tenant FK on ``source_cost_center_id``. UNIQUE(tenant, code); audited (D-010)."""

    __tablename__ = "fin_allocation_rules"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "code", name="uq_fin_allocation_rules_tenant_id_code"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("fin_cost_centers", "source_cost_center_id"),
    )

    code: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    source_cost_center_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    basis: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=AllocationBasis.PERCENT.value,
        server_default="PERCENT",
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )


class AllocationRuleTarget(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """One target of an allocation rule (PLAN 4.7): a (rule, target cost centre, weight) row. The
    ``weight`` is a percent (PERCENT basis) or a fixed weight (FIXED_WEIGHT basis) — MoneyType so it
    round-trips exactly on both engines (D-015). UNIQUE(tenant, rule, target) so a rule lists each
    target once. Both ``allocation_rule_id`` and ``target_cost_center_id`` are composite tenant FKs.
    Audited (D-010): the split is configuration that changes where cost lands."""

    __tablename__ = "fin_allocation_rule_targets"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        # Abbreviated explicit names: the D-022 column-0 auto name for these composite FKs / the
        # unique would overflow PG's 63-char identifier cap, so the model + migration share the
        # short name (keeping autogenerate drift-free).
        sa.ForeignKeyConstraint(
            ["tenant_id", "allocation_rule_id"],
            ["fin_allocation_rules.tenant_id", "fin_allocation_rules.id"],
            name="fk_fin_alloc_rule_targets_tenant_id_rules",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "target_cost_center_id"],
            ["fin_cost_centers.tenant_id", "fin_cost_centers.id"],
            name="fk_fin_alloc_rule_targets_tenant_id_cost_centers",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "allocation_rule_id",
            "target_cost_center_id",
            name="uq_fin_alloc_rule_targets_rule_target",
        ),
    )

    allocation_rule_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    target_cost_center_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    weight: Mapped[object] = mapped_column(MoneyType(), nullable=False)


class AllocationRun(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, DocumentMixin, Base):
    """Bookkeeping for one execution of an allocation rule for a period (PLAN 4.7). DocumentMixin so
    the run cannot exist without a registry entry; the gapless ``run_number`` is claimed at posting
    (D-012). ``allocated_amount`` is the source cost centre's net period balance that was
    redistributed; ``journal_entry_id`` (composite tenant FK) links the posted entry carrying the
    cost-centre dimension per line. ``status`` is POSTED (or REVERSED once its entry is reversed).
    Composite tenant FK on ``fiscal_period_id``. Audited (D-010): an allocation run posts to the
    GL."""

    __tablename__ = "fin_allocation_runs"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        tenant_fk("fin_allocation_rules", "allocation_rule_id"),
        tenant_fk("fin_fiscal_periods", "fiscal_period_id"),
        tenant_fk("fin_journal_entries", "journal_entry_id"),
    )

    allocation_rule_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    fiscal_period_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    run_number: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    run_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    allocated_amount: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    status: Mapped[str] = mapped_column(
        sa.String(12),
        nullable=False,
        default=AllocationRunStatus.POSTED.value,
        server_default="POSTED",
    )
