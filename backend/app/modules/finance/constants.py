"""Finance enums, the normal-balance mapping, and this module's permission keys.

Enums are StrEnum so their UPPER_SNAKE values store directly as strings (STRUCTURE §7:
"values UPPER_SNAKE stored as strings"); core columns are plain ``sa.String`` and the
service maps to/from these classes, matching how core stores its status values (no
``sa.Enum``). Permission keys are ``finance.entity.action`` and are registered into the
core RBAC catalog at import (D-009) so tenants can only ever be granted keys some endpoint
actually checks; only the keys THIS task's endpoints check are added here — journal, AP and
AR keys arrive with their tasks (4.2+).
"""

from enum import StrEnum

from app.core.rbac import register_permissions


class AccountType(StrEnum):
    """The five statement-deriving account types (D-021). All financial statements project
    from journal lines grouped by the account's type, so this set is the minimal metadata
    from which the trial balance, P&L, balance sheet and cash-flow statement derive."""

    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


class NormalBalance(StrEnum):
    """The side on which an account normally carries a positive balance. Derivable from
    account_type but stored on the account for query simplicity (D-021)."""

    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class CashFlowCategory(StrEnum):
    """Cash-flow-statement bucket for an account (D-021). Nullable on the account: only
    accounts that participate in the indirect cash-flow statement carry one."""

    OPERATING = "OPERATING"
    INVESTING = "INVESTING"
    FINANCING = "FINANCING"


class PeriodStatus(StrEnum):
    """Open/closed state of a fiscal year or period (D-018). A period (or year) that is
    CLOSED rejects postings dated within it — enforced at the service layer now and, once
    the journal exists (4.2), at the DB level by the period-posting trigger."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"


class EntryStatus(StrEnum):
    """Lifecycle of a journal entry (D-017). DRAFT is editable; POSTED is immutable (only the
    transition to REVERSED is allowed, with reversed_by set); REVERSED marks an entry that a
    reversing entry has cancelled. The DB immutability trigger enforces the same transitions."""

    DRAFT = "DRAFT"
    POSTED = "POSTED"
    REVERSED = "REVERSED"


class DocumentType(StrEnum):
    """Journal-entry document type (D-017). JOURNAL is a manual/general entry; the others tag
    entries produced by specific flows so projections and the document registry can group them.
    Stored as the UPPER_SNAKE string on the entry; the reversal of any entry preserves the
    original's type so a reversed FX_REVAL stays an FX_REVAL pair."""

    JOURNAL = "JOURNAL"
    AP_INVOICE = "AP_INVOICE"
    AR_INVOICE = "AR_INVOICE"
    PAYMENT = "PAYMENT"
    COGS = "COGS"
    FX_REVAL = "FX_REVAL"
    DEPRECIATION = "DEPRECIATION"


class RateKind(StrEnum):
    """Exchange-rate type (D-019). SPOT is the day's rate used for posting-time translation;
    CLOSING is the period-end rate used for unrealized-FX revaluation. Stored as the UPPER_SNAKE
    string on fin_exchange_rates; get_rate filters on it so a posting and a revaluation never
    accidentally share a rate."""

    SPOT = "SPOT"
    CLOSING = "CLOSING"


class FxRunStatus(StrEnum):
    """Status of an FX revaluation run (D-019). A run is COMPLETED once it has posted its
    FX_REVAL entries and their next-period auto-reversals; re-running a period first REVERSES the
    previous run (append-only, never delete) — marking it REVERSED — then posts a fresh
    COMPLETED run. DRAFT is the transient pre-post state."""

    DRAFT = "DRAFT"
    COMPLETED = "COMPLETED"
    REVERSED = "REVERSED"


# core_documents doc_type for a journal entry (D-012 namespaced constant). Registered with the
# entry at creation; the partial-unique (tenant, doc_number) index backstops gapless numbering.
JOURNAL_ENTRY_DOC_TYPE = "finance.journal_entry"

# core/numbering sequence key + format for journal entry numbers (D-012). The sequence
# year-resets so numbers read JE-2026-00001; claimed at posting, never at draft creation.
JOURNAL_SEQUENCE_NAME = "finance.journal"
JOURNAL_NUMBER_PREFIX = "JE"
JOURNAL_NUMBER_PADDING = 5


# --- FX posting-default purposes (D-019) --------------------------------------
# The data-driven account wiring keys for fin_posting_defaults. The FX engine resolves these to
# GL accounts via service/fx.get_posting_default, so account selection is configuration, not code.
# Realized FX (gain/loss at clearing) is wired now for AP/AR (4.4+); unrealized FX (gain/loss at
# revaluation) + the balance-sheet adjustment account are used by the revaluation run here.
FX_REALIZED_GAIN = "fx_realized_gain"
FX_REALIZED_LOSS = "fx_realized_loss"
FX_UNREALIZED_GAIN = "fx_unrealized_gain"
FX_UNREALIZED_LOSS = "fx_unrealized_loss"
FX_REVALUATION_ADJUSTMENT = "fx_revaluation_adjustment"

# The full set of FX purposes, for validation (set_posting_default accepts only known purposes).
FX_POSTING_PURPOSES: frozenset[str] = frozenset(
    {
        FX_REALIZED_GAIN,
        FX_REALIZED_LOSS,
        FX_UNREALIZED_GAIN,
        FX_UNREALIZED_LOSS,
        FX_REVALUATION_ADJUSTMENT,
    }
)

# docflow link type joining a revaluation run's adjustment entry to its auto-reversal, and the
# run-bookkeeping doc_type is not needed (runs are tracked in fin_fx_revaluation_runs, not the
# document registry) — the FX_REVAL entries themselves register as journal documents (D-012).
FX_REVALUES_LINK = "revalues"


# account_type -> the side it normally carries (D-021). ASSET/EXPENSE accumulate on the
# debit side; LIABILITY/EQUITY/REVENUE on the credit side. The service uses this to default
# normal_balance when a caller does not supply one, so the stored value can never disagree
# with the type.
_NORMAL_BALANCE_BY_TYPE: dict[AccountType, NormalBalance] = {
    AccountType.ASSET: NormalBalance.DEBIT,
    AccountType.EXPENSE: NormalBalance.DEBIT,
    AccountType.LIABILITY: NormalBalance.CREDIT,
    AccountType.EQUITY: NormalBalance.CREDIT,
    AccountType.REVENUE: NormalBalance.CREDIT,
}


def normal_balance_for(account_type: AccountType) -> NormalBalance:
    """The normal balance implied by an account type (D-021). Total mapping over the five
    types, so this never raises for a valid AccountType."""
    return _NORMAL_BALANCE_BY_TYPE[account_type]


# --- Permission keys (D-009) --------------------------------------------------
# Only the keys this task's endpoints guard. Journal/AP/AR/payment keys are registered by
# their own tasks (4.2+) when those endpoints exist.
FINANCE_ACCOUNT_READ = "finance.account.read"
FINANCE_ACCOUNT_MANAGE = "finance.account.manage"
FINANCE_PERIOD_READ = "finance.period.read"
FINANCE_PERIOD_MANAGE = "finance.period.manage"
FINANCE_JOURNAL_READ = "finance.journal.read"
FINANCE_JOURNAL_POST = "finance.journal.post"
FINANCE_JOURNAL_REVERSE = "finance.journal.reverse"
# FX (D-019): manage currencies/rates/posting-defaults vs run a revaluation.
FINANCE_FX_MANAGE = "finance.fx.manage"
FINANCE_FX_REVALUE = "finance.fx.revalue"

register_permissions(
    FINANCE_ACCOUNT_READ,
    FINANCE_ACCOUNT_MANAGE,
    FINANCE_PERIOD_READ,
    FINANCE_PERIOD_MANAGE,
    FINANCE_JOURNAL_READ,
    FINANCE_JOURNAL_POST,
    FINANCE_JOURNAL_REVERSE,
    FINANCE_FX_MANAGE,
    FINANCE_FX_REVALUE,
    descriptions={
        FINANCE_ACCOUNT_READ: "Read the chart of accounts and account groups",
        FINANCE_ACCOUNT_MANAGE: "Create and edit accounts and account groups",
        FINANCE_PERIOD_READ: "Read fiscal years and periods",
        FINANCE_PERIOD_MANAGE: "Create fiscal years and open/close periods",
        FINANCE_JOURNAL_READ: "Read journal entries and their lines",
        FINANCE_JOURNAL_POST: "Create draft journal entries and post them",
        FINANCE_JOURNAL_REVERSE: "Reverse posted journal entries",
        FINANCE_FX_MANAGE: "Manage currencies, exchange rates and posting defaults",
        FINANCE_FX_REVALUE: "Run foreign-currency revaluation",
    },
)
