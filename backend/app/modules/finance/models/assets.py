"""Asset accounting lite (PLAN 4.10): register, depreciation runs, per-asset-period entries.

Three tables, the eighth file in the finance ``models/`` package (STRUCTURE §3):

- ``Asset`` (``fin_assets``): one fixed asset. DocumentMixin (registered at creation, doc_number
  NULL); the gapless AST number is claimed at ACTIVATION — the D-012 claim-at-permanence moment
  for an asset, so ``asset_number`` is nullable with a partial unique index. The three account
  links (asset BS account, accumulated-depreciation contra account, depreciation-expense
  account) are composite tenant FKs to fin_accounts with explicit names (the D-022 column-0
  convention would collide three ways). ``cost_center_id`` is an opaque dimension Uuid (the
  journal-line precedent — validated at the service layer, D-022).
- ``DepreciationRun`` (``fin_depreciation_runs``): bookkeeping for one run of a fiscal period
  (the allocation-run pattern): DocumentMixin + DEP number claimed at posting, link to the ONE
  grouped journal entry, total + asset count.
- ``DepreciationEntry`` (``fin_depreciation_entries``): one asset's depreciation in one period.
  UNIQUE(tenant, asset, fiscal_period) is the run's IDEMPOTENCY BACKBONE — an asset depreciates
  once per period, ever; concurrent/overlapping runs collide here. ``accumulated_after`` /
  ``nbv_after`` are the per-entry audit trail; the register report RECOMPUTES from SUM(amount)
  (no stored NBV on the asset — projections over the entries, D-021 spirit). NOT AuditMixin:
  rows are bulk-inserted once (PERFORMANCE §2) and never mutated; the run header is audited.

Money columns are MoneyType (D-015). Enum-valued columns are plain ``sa.String`` storing the
StrEnum value; the service maps to/from the constants classes.
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
from app.modules.finance.constants import AssetStatus, DepreciationRunStatus


class Asset(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, DocumentMixin, Base):
    """A fixed asset (PLAN 4.10). DRAFT until activated; activation claims the AST number and
    optionally posts the acquisition journal (Dr asset account / Cr acquisition clearing) —
    ``capitalized_journal_entry_id`` links that entry. FULLY_DEPRECIATED once accumulated
    depreciation reaches cost - salvage. Audited (D-010): the register is financial master
    data."""

    __tablename__ = "fin_assets"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        # Three FKs to fin_accounts: the D-022 column-0 auto name would collide, so each
        # carries an explicit (<63 char) name.
        sa.ForeignKeyConstraint(
            ["tenant_id", "asset_account_id"],
            ["fin_accounts.tenant_id", "fin_accounts.id"],
            name="fk_fin_assets_tenant_id_asset_account",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "accumulated_depreciation_account_id"],
            ["fin_accounts.tenant_id", "fin_accounts.id"],
            name="fk_fin_assets_tenant_id_accum_depr_account",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "depreciation_expense_account_id"],
            ["fin_accounts.tenant_id", "fin_accounts.id"],
            name="fk_fin_assets_tenant_id_depr_expense_account",
        ),
        tenant_fk("fin_journal_entries", "capitalized_journal_entry_id"),
        # The depreciation run's eligibility scan: ACTIVE assets per tenant (PERFORMANCE §1).
        sa.Index("ix_fin_assets_tenant_id_status", "tenant_id", "status"),
    )

    # NULL until activation (D-012 claim-at-permanence); partial unique index below backstops.
    asset_number: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    acquisition_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    acquisition_cost: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    salvage_value: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )
    useful_life_months: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    depreciation_method: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    # Annual percentage (e.g. 20.0 = 20%/yr); required when method = DECLINING_BALANCE.
    declining_rate_percent: Mapped[object] = mapped_column(MoneyType(), nullable=True)
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, default=AssetStatus.DRAFT.value, server_default="DRAFT"
    )
    asset_account_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    accumulated_depreciation_account_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, nullable=False
    )
    depreciation_expense_account_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    # Opaque dimension (no FK — the journal-line precedent; service validates, D-022).
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    capitalized_journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid, nullable=True
    )


class DepreciationRun(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, DocumentMixin, Base):
    """One depreciation run for a fiscal period (PLAN 4.10, the allocation-run pattern).
    DocumentMixin so the run cannot exist without a registry entry; the gapless ``run_number``
    is claimed at posting (D-012). ``journal_entry_id`` links the ONE grouped journal entry the
    run posted; ``total_amount`` / ``asset_count`` summarize it. Audited (D-010): a run posts
    to the GL."""

    __tablename__ = "fin_depreciation_runs"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        tenant_fk("fin_fiscal_periods", "fiscal_period_id"),
        tenant_fk("fin_journal_entries", "journal_entry_id"),
        # The idempotency probe: an existing POSTED run for (tenant, period) (PERFORMANCE §1).
        sa.Index(
            "ix_fin_depreciation_runs_tenant_id_fiscal_period_id",
            "tenant_id",
            "fiscal_period_id",
        ),
    )

    fiscal_period_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    run_number: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    run_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(12),
        nullable=False,
        default=DepreciationRunStatus.POSTED.value,
        server_default="POSTED",
    )
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    total_amount: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )
    asset_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default="0"
    )


class DepreciationEntry(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One asset's depreciation in one fiscal period (PLAN 4.10). The UNIQUE(tenant, asset,
    period) constraint is the run's idempotency backbone (module docstring). ``amount`` is the
    period charge; ``accumulated_after`` / ``nbv_after`` freeze the running totals after this
    entry for the audit trail — the register recomputes from SUM(amount), never reads a stored
    asset total."""

    __tablename__ = "fin_depreciation_entries"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("fin_depreciation_runs", "run_id"),
        tenant_fk("fin_assets", "asset_id"),
        tenant_fk("fin_fiscal_periods", "fiscal_period_id"),
        # An asset depreciates ONCE per period, ever (also covers the asset_id FK prefix).
        sa.UniqueConstraint(
            "tenant_id",
            "asset_id",
            "fiscal_period_id",
            name="uq_fin_depreciation_entries_asset_period",
        ),
        # The run's entry list + the run_id FK (PERFORMANCE §1).
        sa.Index("ix_fin_depreciation_entries_tenant_id_run_id", "tenant_id", "run_id"),
        # The register's as-of period bound + the fiscal_period_id FK (PERFORMANCE §1).
        sa.Index(
            "ix_fin_depreciation_entries_tenant_id_fiscal_period_id",
            "tenant_id",
            "fiscal_period_id",
        ),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    fiscal_period_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    amount: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    accumulated_after: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    nbv_after: Mapped[object] = mapped_column(MoneyType(), nullable=False)


# Gapless asset numbers: many drafts may have NULL asset_number, never two the SAME (D-012).
# Declared outside the class so the predicate is a column expression (the D-007 grep gate bans
# raw SQL under app/modules/); both dialect kwargs are required (each engine needs its own).
sa.Index(
    "uq_fin_assets_tenant_id_asset_number",
    Asset.tenant_id,
    Asset.asset_number,
    unique=True,
    postgresql_where=Asset.asset_number.isnot(None),
    sqlite_where=Asset.asset_number.isnot(None),
)
