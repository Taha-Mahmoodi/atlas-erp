"""Multi-currency master data + posting-default wiring (D-019).

Four tables, the third file in the finance ``models/`` package (STRUCTURE §3):

- ``Currency`` (``fin_currencies``): the tenant's currency catalog. Exactly one row per tenant
  is the FUNCTIONAL currency (the books' reporting currency); the one-functional invariant is
  enforced by the service (``service/fx.set_functional_currency``) and the partial unique index
  declared below backstops it at the DB on both engines.
- ``ExchangeRate`` (``fin_exchange_rates``): a rate for a (from, to, rate_type) pair on a date.
  ``get_rate`` picks the most recent rate with ``rate_date <= on_date`` (D-019: postings never
  guess — a missing rate is a hard 422). ``rate`` is ``RateType`` (NUMERIC(20,10) / nano-unit
  ints, D-015) so rates keep full precision and are never quantized to currency decimals.
- ``PostingDefault`` (``fin_posting_defaults``): purpose-keyed account wiring (D-019). One row
  per (tenant, purpose) maps a purpose string (e.g. ``'fx_unrealized_gain'``) to an account, so
  the FX engine — and later AP/AR/inventory COGS — resolve accounts data-driven rather than
  hard-coded.
- ``FxRevaluationRun`` (``fin_fx_revaluation_runs``): bookkeeping for one unrealized-FX
  revaluation run (D-019). Tracks the run's period, rate_date and status; its posted entries are
  linked via docflow (``'revalues'`` edges) so a re-run can reverse exactly the prior run's
  entries (append-only, never delete).

All four follow the D-007 composite-tenant-FK backstop. Enum-valued columns are plain
``sa.String`` storing the StrEnum value (matching the rest of finance); the service maps
to/from the constants classes.
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
from app.core.money import RateType
from app.modules.finance.constants import FxRunStatus, RateKind


class Currency(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A currency in the tenant's catalog (D-019). ``code`` is the ISO-4217 alpha code
    (e.g. ``'USD'``); ``decimal_places`` is the minor-unit scale used to quantize posting
    amounts (default 2; JPY=0, BHD=3). Exactly one currency per tenant has ``is_functional``
    TRUE — the books' reporting currency. Audited (D-010): currency config is master data."""

    __tablename__ = "fin_currencies"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "code", name="uq_fin_currencies_tenant_id_code"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
    )

    code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    decimal_places: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=2, server_default="2"
    )
    is_functional: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )


class ExchangeRate(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """One exchange rate (D-019). A (tenant, rate_date, from, to, rate_type) row gives the
    ``rate`` to multiply a ``from_currency_code`` amount by to get ``to_currency_code``.
    ``rate_type`` is SPOT (posting-time translation) or CLOSING (period-end revaluation).
    Audited (D-010): rate edits change historical translation if mis-dated, so they are
    tracked."""

    __tablename__ = "fin_exchange_rates"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "rate_date",
            "from_currency_code",
            "to_currency_code",
            "rate_type",
            name="uq_fin_exchange_rates_pair",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        # The hot lookup get_rate runs on every foreign-currency posting: the most recent rate
        # for a (pair, type) with rate_date <= on_date.
        sa.Index(
            "ix_fin_exchange_rates_lookup",
            "tenant_id",
            "from_currency_code",
            "to_currency_code",
            "rate_type",
            "rate_date",
        ),
    )

    rate_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    from_currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    to_currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    rate_type: Mapped[str] = mapped_column(
        sa.String(10), nullable=False, default=RateKind.SPOT.value, server_default="SPOT"
    )
    rate: Mapped[object] = mapped_column(RateType(), nullable=False)


class PostingDefault(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """Purpose-keyed account wiring (D-019). One row per (tenant, purpose) maps a purpose
    string to a GL account, so flows that must post to a configured account (FX gain/loss,
    revaluation adjustment, later AP/AR/COGS) resolve it data-driven via
    ``service/fx.get_posting_default``. Composite tenant FK to fin_accounts. Audited (D-010):
    account wiring is configuration that changes where money lands."""

    __tablename__ = "fin_posting_defaults"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "purpose", name="uq_fin_posting_defaults_tenant_id_purpose"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("fin_accounts", "account_id"),
    )

    purpose: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)


class FxRevaluationRun(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """Bookkeeping for one unrealized-FX revaluation run (D-019). ``fiscal_period_id`` is the
    period being revalued (composite tenant FK); ``rate_date`` is the CLOSING-rate date (the
    period end). ``status`` is DRAFT->COMPLETED while running, or REVERSED once a later run has
    reversed this run's entries. The run's posted FX_REVAL entries are linked via docflow
    (``'revalues'`` edges) so a re-run reverses exactly the prior run's entries — append-only,
    never delete. Audited (D-010): a revaluation run posts to the GL."""

    __tablename__ = "fin_fx_revaluation_runs"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("fin_fiscal_periods", "fiscal_period_id"),
    )

    fiscal_period_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    rate_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(12),
        nullable=False,
        default=FxRunStatus.COMPLETED.value,
        server_default="COMPLETED",
    )


# One functional currency per tenant (D-019): a partial unique index on (tenant_id) WHERE
# is_functional, so a second functional currency is rejected at the DB on both engines. Declared
# outside the class so the predicate is a column expression (the D-007 grep gate bans raw-SQL
# under app/modules/); both dialect kwargs are required (each engine needs its own predicate).
sa.Index(
    "uq_fin_currencies_one_functional",
    Currency.tenant_id,
    unique=True,
    postgresql_where=Currency.is_functional,
    sqlite_where=Currency.is_functional,
)
