"""Finance models: chart of accounts (D-021) and fiscal years/periods (D-018).

Per D-021 the account-type model here is exactly what later statement projections consume:
``account_type`` drives every statement (trial balance, P&L, balance sheet, cash flow), the
``account_group`` tree is a PURE PRESENTATION hierarchy (accounts hang off groups; the
hierarchy lives on the GROUP tree's ``parent_id``, not on accounts — so accounts have no
``parent_id``, resolving the task's "parent_id OR account_group" choice in favour of D-021),
and ``cash_flow_category`` + ``is_cash_equivalent`` feed the indirect cash-flow statement.

Enum-valued columns are plain ``sa.String`` storing the StrEnum's UPPER_SNAKE value, matching
how core stores status values (no ``sa.Enum``); the service maps to/from the constants classes.
All four tables follow the D-007 composite-tenant-FK backstop: tenant_unique() on every table
that is referenced, tenant_fk() composites for every cross-row link so a child can never point
at another tenant's parent.
"""

import uuid
from datetime import date

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
from app.modules.finance.constants import PeriodStatus


class AccountGroup(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A node in the chart-of-accounts presentation hierarchy (D-021). Pure presentation:
    groups carry no postings and no balances; ``parent_id`` builds the tree and accounts
    reference a group via ``account_group_id``. ``sort_order`` orders siblings in the UI.
    Audited (D-010): the COA layout is configuration."""

    __tablename__ = "fin_account_groups"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "code", name="uq_fin_account_groups_tenant_id_code"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        # Self-referential composite tenant FK: a group's parent must be in the same tenant.
        tenant_fk("fin_account_groups", "parent_id"),
    )

    code: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    # server_default is a bare string literal "0" rather than a Core SQL clause: the D-007
    # grep gate bans raw-SQL constructs under app/modules/, and "0" is a portable integer
    # default on both engines. The migration renders the identical default in alembic/, which
    # the gate exempts.
    sort_order: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default="0"
    )


class Account(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A general-ledger account (D-021). ``account_type`` is the load-bearing field every
    statement projects from; ``normal_balance`` is derivable from the type but stored for
    query simplicity (the service defaults it from the type so the two never disagree).
    Only postable (leaf) accounts accept journal lines — ``is_postable`` gates that, checked
    by the journal posting service in 4.2. ``cash_flow_category`` + ``is_cash_equivalent``
    feed the indirect cash-flow statement. Audited (D-010): master data."""

    __tablename__ = "fin_accounts"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "code", name="uq_fin_accounts_tenant_id_code"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        # Composite tenant FK: an account's group must belong to the same tenant.
        tenant_fk("fin_account_groups", "account_group_id"),
    )

    code: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    # Stored as the AccountType / NormalBalance / CashFlowCategory string value.
    account_type: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    normal_balance: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    is_postable: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    cash_flow_category: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    is_cash_equivalent: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    account_group_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )


class FiscalYear(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A fiscal year (D-018). Owns N periods; ``status`` lets a year be CLOSED only after
    all its periods are closed (the service enforces that). Audited (D-010): closing a year
    is a controlled accounting action."""

    __tablename__ = "fin_fiscal_years"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "code", name="uq_fin_fiscal_years_tenant_id_code"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        sa.CheckConstraint("start_date <= end_date", name="ck_fin_fiscal_years_date_order"),
    )

    code: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    start_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    end_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(10), nullable=False, default=PeriodStatus.OPEN.value, server_default="OPEN"
    )


class FiscalPeriod(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A posting period within a fiscal year (D-018). The journal resolves an entry's period
    from its posting_date via the (tenant_id, start_date, end_date) lookup index below;
    closing a period rejects postings dated within it. Audited (D-010): close/open are
    controlled accounting actions."""

    __tablename__ = "fin_fiscal_periods"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "fiscal_year_id",
            "period_number",
            name="uq_fin_fiscal_periods_tenant_id_fiscal_year_id_period_number",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("fin_fiscal_years", "fiscal_year_id"),
        sa.CheckConstraint("start_date <= end_date", name="ck_fin_fiscal_periods_date_order"),
        # The date -> period lookup the journal uses on every posting (4.2): "the period
        # covering posting_date" filters on (tenant_id, start_date, end_date).
        sa.Index(
            "ix_fin_fiscal_periods_tenant_id_start_date_end_date",
            "tenant_id",
            "start_date",
            "end_date",
        ),
    )

    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    period_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    name: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    start_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    end_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(10), nullable=False, default=PeriodStatus.OPEN.value, server_default="OPEN"
    )
