"""The universal journal: header + lines (D-017), the heart of Atlas finance.

One append-only line table is the single source of truth for every FI/CO view (D-021); the
header carries entry-level lifecycle and the lines carry the postings plus every dimension a
statement projects from. Denormalized ``is_posted``/``posting_date``/``fiscal_period_id`` on the
line (set during the two-flush posting protocol) let projections query lines with NO header join
(D-021), which is why those columns live on the line at all.

Money columns use ``MoneyType`` (D-015): exact NUMERIC on Postgres, INTEGER micro-units on
SQLite, so the balance trigger's SUM and the one-side CHECK are exact on both engines. For v1,
functional amounts EQUAL transaction amounts (single functional currency, posting-time FX
translation lands in 4.3) — the columns exist now so the schema and triggers are FX-ready.

Constraints declared here (rendered by migration 0009):
- ``ck_fin_journal_lines_one_side``: exactly one of debit/credit positive per line, the other
  zero — written on the stored columns so it holds on PG NUMERIC and SQLite micro-unit ints.
- the per-dialect TRIGGERS (period-open, balance, header immutability, line immutability) are
  NOT model constraints; they are hand-written DDL in the migration (D-017/D-018/D-022).

Dimension columns (cost_center_id, profit_center_id, project_id, item_id, partner_id) are plain
``sa.Uuid`` WITHOUT FKs for now: the CO/project/inventory masters land in later PLAN phases
(4.7 controlling, 5 inventory, 11 projects); the ids are stored on the line today and FK'd when
those parent tables exist. partner_type + partner_id carry AP/AR open-item linkage (4.4+).
"""

import uuid
from datetime import date, datetime

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
from app.modules.finance.constants import DocumentType, EntryStatus

# Bare CHECK token (the D-022 ck convention wraps it as ck_<table>_<name>). Compares the STORED
# representation (NUMERIC on PG, micro-unit INTEGER on SQLite) so "> 0" / "= 0" hold on both.
_ONE_SIDE_CHECK = (
    "(transaction_debit_amount > 0 AND transaction_credit_amount = 0) "
    "OR (transaction_credit_amount > 0 AND transaction_debit_amount = 0)"
)


class JournalEntry(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, DocumentMixin, Base):
    """A journal-entry header (D-017). Registered in core_documents at creation (DocumentMixin)
    with doc_number NULL; the gapless ``entry_number`` is claimed at POSTING (D-012), so an
    abandoned draft burns no number — hence ``entry_number`` is NULLABLE with a partial unique
    index. An entry is single-transaction-currency (cross-currency events become multiple
    entries). ``reverses_entry_id`` points at the original an entry reverses;
    ``reversed_by_entry_id`` points at the reversing entry — both self composite tenant FKs.
    Audited (D-010): every financial mutation is auditable."""

    __tablename__ = "fin_journal_entries"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        # Self composite tenant FKs: a reversal linkage can never cross tenants. Distinct
        # explicit names (the D-022 column-0 convention would collide on two self-FKs).
        sa.ForeignKeyConstraint(
            ["tenant_id", "reverses_entry_id"],
            ["fin_journal_entries.tenant_id", "fin_journal_entries.id"],
            name="fk_fin_journal_entries_reverses_entry_id_fin_journal_entries",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reversed_by_entry_id"],
            ["fin_journal_entries.tenant_id", "fin_journal_entries.id"],
            name="fk_fin_journal_entries_reversed_by_entry_id_fin_journal_entries",
        ),
        # Composite tenant FK: the resolved period belongs to the same tenant.
        tenant_fk("fin_fiscal_periods", "fiscal_period_id"),
        # The gapless-number partial unique index is declared after the class (it needs the
        # column object for its dialect partial predicate, expressed without raw SQL so the
        # app/modules grep gate stays satisfied — see below).
    )

    # NULL until posting (D-012 claim-at-permanence); the partial unique index above backstops it.
    entry_number: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    posting_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    # Resolved from posting_date at posting (D-018); nullable until then. The DB period trigger
    # re-derives by date so a wrong fiscal_period_id can never smuggle a posting into a closed
    # period.
    fiscal_period_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    document_type: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, default=DocumentType.JOURNAL.value, server_default="JOURNAL"
    )
    currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        sa.String(10), nullable=False, default=EntryStatus.DRAFT.value, server_default="DRAFT"
    )
    reverses_entry_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    reversed_by_entry_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class JournalLine(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """A journal line (D-017): one posting on one account, one-sided (debit XOR credit). NOT
    AuditMixin — lines are written once with their immutable entry and never mutated after the
    posting flush, and the header's audit row records the entry-level change; auditing every
    line would double the trail with no extra signal (documented exclusion). The denormalized
    ``is_posted``/``posting_date``/``fiscal_period_id`` are set during the DRAFT->POSTED flush so
    statement projections read lines with no header join (D-021)."""

    __tablename__ = "fin_journal_lines"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "journal_entry_id",
            "line_number",
            name="uq_fin_journal_lines_tenant_id_journal_entry_id_line_number",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("fin_journal_entries", "journal_entry_id"),
        tenant_fk("fin_accounts", "account_id"),
        sa.CheckConstraint(_ONE_SIDE_CHECK, name="one_side"),
        # The statement-projection partial index is declared after the class (see below).
    )

    journal_entry_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    line_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)

    # Transaction-currency amounts (the entry's currency). Exactly one side is > 0 (one-side
    # CHECK). MoneyType: exact on both engines so the balance trigger's SUM is exact.
    transaction_debit_amount: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )
    transaction_credit_amount: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )
    # Functional-currency amounts. v1: equal to the transaction amounts (single functional
    # currency; posting-time FX translation in 4.3). The balance trigger SUM-checks THESE.
    functional_debit_amount: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )
    functional_credit_amount: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )
    currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)

    # Dimensions (all nullable; no FK yet — masters land in later phases, see module docstring).
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    profit_center_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    item_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    # AP/AR open-item linkage (4.4+): partner_type ('VENDOR'|'CUSTOMER') + partner_id.
    partner_type: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    partner_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)

    # Denormalized for statement projection (D-021): set during the posting transaction so a
    # projection queries lines with no header join.
    is_posted: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    posting_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    fiscal_period_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)


# Partial indexes declared OUTSIDE the class bodies so their dialect predicate is a column
# expression (``.isnot(None)`` / the boolean column) rather than a raw SQL string literal — the
# D-007 grep gate bans raw-SQL constructs under app/modules/. Both dialect kwargs are required
# (each engine needs its own partial-index predicate, D-012/D-021); the migration renders the same.

# Gapless numbers: many drafts may have NULL entry_number, never two the SAME (D-012).
sa.Index(
    "uq_fin_journal_entries_tenant_id_entry_number",
    JournalEntry.tenant_id,
    JournalEntry.entry_number,
    unique=True,
    postgresql_where=JournalEntry.entry_number.isnot(None),
    sqlite_where=JournalEntry.entry_number.isnot(None),
)

# Statement-projection covering index (D-021): lines grouped by account over a date range, only
# the posted ones.
sa.Index(
    "ix_fin_journal_lines_proj",
    JournalLine.tenant_id,
    JournalLine.account_id,
    JournalLine.posting_date,
    postgresql_where=JournalLine.is_posted,
    sqlite_where=JournalLine.is_posted,
)
