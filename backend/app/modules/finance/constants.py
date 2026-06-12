"""Finance enums, the normal-balance mapping, and this module's permission keys.

Enums are StrEnum so their UPPER_SNAKE values store directly as strings (STRUCTURE §7);
core columns are plain ``sa.String`` and the service maps to/from these classes (no
``sa.Enum``). Permission keys are ``finance.entity.action`` and register into the core
RBAC catalog at import (D-009) so tenants can only be granted keys an endpoint checks.
"""

from enum import StrEnum

from app.core.rbac import register_permissions


class AccountType(StrEnum):
    """The five statement-deriving account types (D-021) — all statements project from
    journal lines grouped by the account's type."""

    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


class NormalBalance(StrEnum):
    """The side an account normally carries a positive balance on; derivable from
    account_type but stored for query simplicity (D-021)."""

    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class CashFlowCategory(StrEnum):
    """Cash-flow-statement bucket (D-021); nullable — only cash-flow accounts carry one."""

    OPERATING = "OPERATING"
    INVESTING = "INVESTING"
    FINANCING = "FINANCING"


class PeriodStatus(StrEnum):
    """Open/closed state of a fiscal year or period (D-018); CLOSED rejects postings dated
    within it — at the service layer and the DB period-posting trigger."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"


class EntryStatus(StrEnum):
    """Journal-entry lifecycle (D-017): DRAFT editable; POSTED immutable (only -> REVERSED,
    with reversed_by set); REVERSED = cancelled by a reversing entry. DB trigger matches."""

    DRAFT = "DRAFT"
    POSTED = "POSTED"
    REVERSED = "REVERSED"


class DocumentType(StrEnum):
    """Journal-entry document type (D-017): JOURNAL = manual entry; the others tag entries
    from specific flows. A reversal preserves the original's type (FX_REVAL stays FX_REVAL)."""

    JOURNAL = "JOURNAL"
    AP_INVOICE = "AP_INVOICE"
    AR_INVOICE = "AR_INVOICE"
    PAYMENT = "PAYMENT"
    COGS = "COGS"
    FX_REVAL = "FX_REVAL"
    DEPRECIATION = "DEPRECIATION"


class TaxDirection(StrEnum):
    """Which side a tax applies to (PLAN 4.4): OUTPUT = charged on a sale, a liability
    posting to ``tax_payable_account_id``; INPUT = paid on a purchase, recoverable, posting
    to ``tax_receivable_account_id``. The calc service picks the account by direction."""

    OUTPUT = "OUTPUT"
    INPUT = "INPUT"


class BillStatus(StrEnum):
    """Vendor-bill lifecycle (PLAN 4.5, AP): DRAFT editable, no number/journal; POSTED has
    number + journal + ``open_amount``; PARTIALLY_PAID/PAID track clearing; REVERSED = journal
    reversed. Open items key on an opaque ``partner_id`` (D-029)."""

    DRAFT = "DRAFT"
    POSTED = "POSTED"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    REVERSED = "REVERSED"


class PaymentStatus(StrEnum):
    """Vendor-payment lifecycle (PLAN 4.5, AP): created+posted in one step (DRAFT transient);
    POSTED has number + clearing journal; REVERSED = journal reversed."""

    DRAFT = "DRAFT"
    POSTED = "POSTED"
    REVERSED = "REVERSED"


class InvoiceStatus(StrEnum):
    """Customer-invoice lifecycle (PLAN 4.6, AR — BillStatus mirror, sign flipped): DRAFT
    editable; POSTED has number + journal + ``open_amount``; PARTIALLY_PAID/PAID track receipt
    clearing; REVERSED = journal reversed. Open items key on opaque ``partner_id`` (D-029)."""

    DRAFT = "DRAFT"
    POSTED = "POSTED"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    REVERSED = "REVERSED"


class ReceiptStatus(StrEnum):
    """Customer-receipt lifecycle (PLAN 4.6, AR — PaymentStatus mirror): created+posted in
    one step (DRAFT transient); POSTED has number + clearing journal; REVERSED = reversed."""

    DRAFT = "DRAFT"
    POSTED = "POSTED"
    REVERSED = "REVERSED"


class AllocationBasis(StrEnum):
    """Allocation-rule target weights (PLAN 4.7): PERCENT must sum to 100; FIXED_WEIGHT are
    positive proportional weights. Parts sum EXACTLY via ``core.money.allocate``."""

    PERCENT = "PERCENT"
    FIXED_WEIGHT = "FIXED_WEIGHT"


class AllocationRunStatus(StrEnum):
    """Allocation-run lifecycle (PLAN 4.7): POSTED (numbered redistribution entry with
    cost_center_id per line), REVERSED, or DRAFT (transient)."""

    DRAFT = "DRAFT"
    POSTED = "POSTED"
    REVERSED = "REVERSED"


class StatementStatus(StrEnum):
    """Bank-statement state (PLAN 4.9), derived from line resolution counts."""

    IMPORTED = "IMPORTED"
    PARTIALLY_RECONCILED = "PARTIALLY_RECONCILED"
    RECONCILED = "RECONCILED"


class LineStatus(StrEnum):
    """Statement-line machine (PLAN 4.9): UNMATCHED -> SUGGESTED -> MATCHED (confirm) or back
    (reject); UNMATCHED -> CLEARED (posted clearing entry). Resolved = MATCHED | CLEARED."""

    UNMATCHED = "UNMATCHED"
    SUGGESTED = "SUGGESTED"
    MATCHED = "MATCHED"
    CLEARED = "CLEARED"


class RateKind(StrEnum):
    """Exchange-rate type (D-019): SPOT = posting-time translation; CLOSING = period-end
    revaluation. get_rate filters on it so the two flows never share a rate."""

    SPOT = "SPOT"
    CLOSING = "CLOSING"


class FxRunStatus(StrEnum):
    """FX revaluation-run status (D-019): COMPLETED once FX_REVAL entries + auto-reversals
    posted; re-running a period REVERSES the prior run (append-only) then posts a fresh
    COMPLETED one; DRAFT is the transient pre-post state."""

    DRAFT = "DRAFT"
    COMPLETED = "COMPLETED"
    REVERSED = "REVERSED"


# Journal doc type + sequence (D-012): registered at creation; the sequence year-resets
# (JE-2026-00001), claimed at posting, never at draft.
JOURNAL_ENTRY_DOC_TYPE = "finance.journal_entry"
JOURNAL_SEQUENCE_NAME = "finance.journal"
JOURNAL_NUMBER_PREFIX = "JE"
JOURNAL_NUMBER_PADDING = 5


# --- Accounts Payable (PLAN 4.5) ----------------------------------------------
# Doc types register at creation (D-012); sequences year-reset (BILL-2026-00001 /
# PAY-2026-00001), claimed at posting only.
AP_BILL_DOC_TYPE = "finance.vendor_bill"
AP_PAYMENT_DOC_TYPE = "finance.vendor_payment"
AP_BILL_SEQUENCE_NAME = "finance.vendor_bill"
AP_BILL_NUMBER_PREFIX = "BILL"
AP_BILL_NUMBER_PADDING = 5
AP_PAYMENT_SEQUENCE_NAME = "finance.vendor_payment"
AP_PAYMENT_NUMBER_PREFIX = "PAY"
AP_PAYMENT_NUMBER_PADDING = 5

# docflow links bill->journal / payment->bills; partner_type tags the AP control line (D-029).
AP_BILL_POSTS_LINK = "posts"
AP_PAYMENT_PAYS_LINK = "pays"
AP_PARTNER_TYPE = "VENDOR"


# --- Accounts Receivable (PLAN 4.6) -------------------------------------------
# The AP mirror sign-flipped (Dr AR control / Cr revenue + output tax; receipts Cr AR /
# Dr bank). Doc types register at creation; sequences year-reset, claimed at posting only.
AR_INVOICE_DOC_TYPE = "finance.customer_invoice"
AR_RECEIPT_DOC_TYPE = "finance.customer_receipt"
AR_INVOICE_SEQUENCE_NAME = "finance.customer_invoice"
AR_INVOICE_NUMBER_PREFIX = "INV"
AR_INVOICE_NUMBER_PADDING = 5
AR_RECEIPT_SEQUENCE_NAME = "finance.customer_receipt"
AR_RECEIPT_NUMBER_PREFIX = "RCT"
AR_RECEIPT_NUMBER_PADDING = 5

# docflow links invoice->journal / receipt->invoices; partner_type tags the AR control line.
AR_INVOICE_POSTS_LINK = "posts"
AR_RECEIPT_RECEIPTS_LINK = "receipts"
AR_PARTNER_TYPE = "CUSTOMER"

# Dunning day-thresholds (PLAN 4.6): highest crossed bound wins; level 0 = no notice yet.
DUNNING_THRESHOLDS: tuple[int, ...] = (7, 30, 60)


def dunning_level_for(days_overdue: int) -> int:
    """The dunning level implied by ``days_overdue`` given DUNNING_THRESHOLDS (PLAN 4.6):
    0 below the first threshold, else the count of thresholds crossed. Total; never raises."""
    level = 0
    for bound in DUNNING_THRESHOLDS:
        if days_overdue >= bound:
            level += 1
        else:
            break
    return level


# --- Controlling: cost/profit centers + allocations (PLAN 4.7) ----------------
# A run posts ONE balanced entry redistributing the source cost centre's cost to its targets on
# the CO_ALLOCATION_CLEARING account, cost_center_id per line; the account nets to zero.
CO_ALLOCATION_DOC_TYPE = "finance.allocation_run"
ALLOCATION_SEQUENCE_NAME = "finance.allocation"
ALLOCATION_NUMBER_PREFIX = "ALLOC"
ALLOCATION_NUMBER_PADDING = 5
CO_ALLOCATION_POSTS_LINK = "posts"
CO_ALLOCATION_CLEARING = "cost_allocation"


# --- FX posting-default purposes (D-019) --------------------------------------
# Data-driven account wiring keys for fin_posting_defaults, resolved via
# service/fx.get_posting_default (account selection is config, not code).
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

# Bank reconciliation (PLAN 4.9): statements register in core_documents with doc_number NULL
# (external documents, not Atlas-numbered); a clearing entry links statement->'posts'->entry.
# Imports above the sync max run as a background job (202 {job_id}, PERFORMANCE §3);
# BANK_UNMATCHED_CLEARING is the suspense posting purpose for clearing bank-only lines.
BANK_STATEMENT_DOC_TYPE = "finance.bank_statement"
BANK_CLEARING_POSTS_LINK = "posts"
BANK_UNMATCHED_CLEARING = "bank_unmatched_clearing"
BANK_IMPORT_SYNC_MAX_LINES = 1000
BANK_STATEMENT_IMPORT_JOB = "finance.bank_statement_import"

# Every known posting-default purpose: FX + the CO/bank clearing accounts; phases extend this.
POSTING_PURPOSES: frozenset[str] = FX_POSTING_PURPOSES | frozenset(
    {CO_ALLOCATION_CLEARING, BANK_UNMATCHED_CLEARING}
)

# docflow link type joining a revaluation run's adjustment entry to its auto-reversal (D-012).
FX_REVALUES_LINK = "revalues"

# Background-job registry keys (PLAN 4P.5/D-032, closes #26): the two long-running finance
# operations execute as jobs — their POST endpoints return 202 {job_id} for /api/v1/jobs polling.
FX_REVALUATION_JOB = "finance.fx_revaluation"
AP_PAYMENT_RUN_JOB = "finance.payment_run"


# account_type -> normal side (D-021): ASSET/EXPENSE debit; LIABILITY/EQUITY/REVENUE credit.
# The service defaults normal_balance from this, so stored value never disagrees with type.
_NORMAL_BALANCE_BY_TYPE: dict[AccountType, NormalBalance] = {
    AccountType.ASSET: NormalBalance.DEBIT,
    AccountType.EXPENSE: NormalBalance.DEBIT,
    AccountType.LIABILITY: NormalBalance.CREDIT,
    AccountType.EQUITY: NormalBalance.CREDIT,
    AccountType.REVENUE: NormalBalance.CREDIT,
}


def normal_balance_for(account_type: AccountType) -> NormalBalance:
    """The normal balance implied by an account type (D-021); total over the five types."""
    return _NORMAL_BALANCE_BY_TYPE[account_type]


# --- Permission keys (D-009) — one key per guarded endpoint action -------------
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
# Tax (PLAN 4.4): read the tax-code catalog vs create/edit tax codes.
FINANCE_TAX_READ = "finance.tax.read"
FINANCE_TAX_MANAGE = "finance.tax.manage"
# Accounts Payable (PLAN 4.5): read bills/payments/aging, create+post bills, run payments.
FINANCE_AP_READ = "finance.ap.read"
FINANCE_AP_MANAGE = "finance.ap.manage"
FINANCE_AP_PAY = "finance.ap.pay"
# Accounts Receivable (PLAN 4.6): read, create+post invoices, collect (receipts + dunning).
FINANCE_AR_READ = "finance.ar.read"
FINANCE_AR_MANAGE = "finance.ar.manage"
FINANCE_AR_COLLECT = "finance.ar.collect"
# Controlling (PLAN 4.7): read vs manage on cost/profit centres + allocation rules; running an
# allocation posts a journal, so it is its own action (D-009).
FINANCE_COST_CENTER_READ = "finance.costcenter.read"
FINANCE_COST_CENTER_MANAGE = "finance.costcenter.manage"
FINANCE_PROFIT_CENTER_READ = "finance.profitcenter.read"
FINANCE_PROFIT_CENTER_MANAGE = "finance.profitcenter.manage"
FINANCE_ALLOCATION_MANAGE = "finance.allocation.manage"
FINANCE_ALLOCATION_RUN = "finance.allocation.run"
# Financial statements (PLAN 4.8, D-021): one read-only key gates all projection statements.
FINANCE_STATEMENTS_READ = "finance.statements.read"
# Bank reconciliation (PLAN 4.9): read, import CSVs, reconcile (suggest/confirm/reject/clear).
FINANCE_BANK_READ = "finance.bank.read"
FINANCE_BANK_IMPORT = "finance.bank.import"
FINANCE_BANK_RECONCILE = "finance.bank.reconcile"

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
    FINANCE_TAX_READ,
    FINANCE_TAX_MANAGE,
    FINANCE_AP_READ,
    FINANCE_AP_MANAGE,
    FINANCE_AP_PAY,
    FINANCE_AR_READ,
    FINANCE_AR_MANAGE,
    FINANCE_AR_COLLECT,
    FINANCE_COST_CENTER_READ,
    FINANCE_COST_CENTER_MANAGE,
    FINANCE_PROFIT_CENTER_READ,
    FINANCE_PROFIT_CENTER_MANAGE,
    FINANCE_ALLOCATION_MANAGE,
    FINANCE_ALLOCATION_RUN,
    FINANCE_STATEMENTS_READ,
    FINANCE_BANK_READ,
    FINANCE_BANK_IMPORT,
    FINANCE_BANK_RECONCILE,
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
        FINANCE_TAX_READ: "Read the tax-code catalog",
        FINANCE_TAX_MANAGE: "Create and edit tax codes",
        FINANCE_AP_READ: "Read vendor bills, payments and AP aging",
        FINANCE_AP_MANAGE: "Create and post vendor bills",
        FINANCE_AP_PAY: "Create vendor payments and run payment batches",
        FINANCE_AR_READ: "Read customer invoices, receipts and AR aging",
        FINANCE_AR_MANAGE: "Create and post customer invoices",
        FINANCE_AR_COLLECT: "Create customer receipts and run dunning",
        FINANCE_COST_CENTER_READ: "Read cost centres",
        FINANCE_COST_CENTER_MANAGE: "Create and edit cost centres",
        FINANCE_PROFIT_CENTER_READ: "Read profit centres",
        FINANCE_PROFIT_CENTER_MANAGE: "Create and edit profit centres",
        FINANCE_ALLOCATION_MANAGE: "Create and edit allocation rules",
        FINANCE_ALLOCATION_RUN: "Run cost allocations",
        FINANCE_STATEMENTS_READ: "Read financial statements (trial balance, P&L, balance sheet, "
        "cash flow, cost-centre and margin reports)",
        FINANCE_BANK_READ: "Read bank statements and their lines",
        FINANCE_BANK_IMPORT: "Import bank statement CSVs",
        FINANCE_BANK_RECONCILE: "Reconcile bank-statement lines (suggest, confirm, clear)",
    },
)
