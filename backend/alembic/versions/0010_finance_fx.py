"""finance multi-currency: currencies, exchange rates, posting defaults, revaluation runs

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-12

PLAN 4.3 / D-019 — multi-currency:

- fin_currencies: the tenant currency catalog. The partial unique index
  ``uq_fin_currencies_one_functional`` ON (tenant_id) WHERE is_functional enforces exactly one
  functional currency per tenant on BOTH engines (both dialect kwargs required, D-019).
- fin_exchange_rates: rates per (rate_date, from, to, rate_type); UNIQUE on that tuple + the
  (tenant, from, to, type, rate_date) lookup index get_rate uses on every foreign posting.
- fin_posting_defaults: purpose-keyed account wiring (UNIQUE(tenant, purpose)); composite tenant
  FK to fin_accounts.
- fin_fx_revaluation_runs: revaluation-run bookkeeping; composite tenant FK to fin_fiscal_periods.

ALSO adds ``is_monetary`` + ``currency_code`` to fin_accounts (the FX revaluation scope, D-019).
This ALTER goes through ``batch_alter_table`` (D-022: every ALTER is batch, pass-through on PG,
copy-rebuild on SQLite). fin_accounts is NOT trigger-bearing — the four journal guard triggers
(migration 0009) live on fin_journal_entries / fin_journal_lines, NOT fin_accounts — so the
SQLite copy-rebuild drops no triggers and there is NO trigger-recreation concern here. The journal
table is deliberately NOT altered (the FX rate override is a post_entry parameter, never persisted
as a column), so its four triggers are untouched. Constraint/index names follow the D-022 naming
convention so SQLite batch mode can drop them later; all DDL is portable across SQLite and Postgres.
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import RateType

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | None = None
depends_on: str | None = None


def _create_currencies() -> None:
    op.create_table(
        "fin_currencies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=3), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("decimal_places", sa.Integer(), server_default="2", nullable=False),
        sa.Column("is_functional", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"],
            name=op.f("fk_fin_currencies_tenant_id_adm_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fin_currencies")),
        sa.UniqueConstraint("tenant_id", "code", name="uq_fin_currencies_tenant_id_code"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_currencies_tenant_id"),
    )
    op.create_index(op.f("ix_fin_currencies_tenant_id"), "fin_currencies", ["tenant_id"])
    # One functional currency per tenant (D-019): partial unique index on both engines.
    op.create_index(
        "uq_fin_currencies_one_functional",
        "fin_currencies",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("is_functional"),
        sqlite_where=sa.text("is_functional"),
    )


def _create_exchange_rates() -> None:
    op.create_table(
        "fin_exchange_rates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("from_currency_code", sa.String(length=3), nullable=False),
        sa.Column("to_currency_code", sa.String(length=3), nullable=False),
        sa.Column("rate_type", sa.String(length=10), server_default="SPOT", nullable=False),
        sa.Column("rate", RateType(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"],
            name=op.f("fk_fin_exchange_rates_tenant_id_adm_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fin_exchange_rates")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_exchange_rates_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "rate_date",
            "from_currency_code",
            "to_currency_code",
            "rate_type",
            name="uq_fin_exchange_rates_pair",
        ),
    )
    op.create_index(op.f("ix_fin_exchange_rates_tenant_id"), "fin_exchange_rates", ["tenant_id"])
    op.create_index(
        "ix_fin_exchange_rates_lookup",
        "fin_exchange_rates",
        ["tenant_id", "from_currency_code", "to_currency_code", "rate_type", "rate_date"],
    )


def _create_posting_defaults() -> None:
    op.create_table(
        "fin_posting_defaults",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=60), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"],
            name=op.f("fk_fin_posting_defaults_tenant_id_adm_tenants"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["fin_accounts.tenant_id", "fin_accounts.id"],
            name=op.f("fk_fin_posting_defaults_account_id_fin_accounts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fin_posting_defaults")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_posting_defaults_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "purpose", name="uq_fin_posting_defaults_tenant_id_purpose"
        ),
    )
    op.create_index(
        op.f("ix_fin_posting_defaults_tenant_id"), "fin_posting_defaults", ["tenant_id"]
    )


def _create_revaluation_runs() -> None:
    op.create_table(
        "fin_fx_revaluation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("fiscal_period_id", sa.Uuid(), nullable=False),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=12), server_default="COMPLETED", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"],
            name=op.f("fk_fin_fx_revaluation_runs_tenant_id_adm_tenants"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "fiscal_period_id"],
            ["fin_fiscal_periods.tenant_id", "fin_fiscal_periods.id"],
            name=op.f("fk_fin_fx_revaluation_runs_fiscal_period_id_fin_fiscal_periods"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fin_fx_revaluation_runs")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_fx_revaluation_runs_tenant_id"),
    )
    op.create_index(
        op.f("ix_fin_fx_revaluation_runs_tenant_id"), "fin_fx_revaluation_runs", ["tenant_id"]
    )


def upgrade() -> None:
    _create_currencies()
    _create_exchange_rates()
    _create_posting_defaults()
    _create_revaluation_runs()

    # FX revaluation scope columns on fin_accounts (D-019). Batch-alter (D-022): pass-through on
    # PG, copy-rebuild on SQLite. fin_accounts carries NO triggers, so the rebuild drops nothing
    # that needs recreating — no trigger-recreation step here (the journal tables are not touched).
    with op.batch_alter_table("fin_accounts") as batch:
        batch.add_column(
            sa.Column("is_monetary", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch.add_column(sa.Column("currency_code", sa.String(length=3), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("fin_accounts") as batch:
        batch.drop_column("currency_code")
        batch.drop_column("is_monetary")

    op.drop_index(
        op.f("ix_fin_fx_revaluation_runs_tenant_id"), table_name="fin_fx_revaluation_runs"
    )
    op.drop_table("fin_fx_revaluation_runs")
    op.drop_index(
        op.f("ix_fin_posting_defaults_tenant_id"), table_name="fin_posting_defaults"
    )
    op.drop_table("fin_posting_defaults")
    op.drop_index("ix_fin_exchange_rates_lookup", table_name="fin_exchange_rates")
    op.drop_index(op.f("ix_fin_exchange_rates_tenant_id"), table_name="fin_exchange_rates")
    op.drop_table("fin_exchange_rates")
    op.drop_index("uq_fin_currencies_one_functional", table_name="fin_currencies")
    op.drop_index(op.f("ix_fin_currencies_tenant_id"), table_name="fin_currencies")
    op.drop_table("fin_currencies")
