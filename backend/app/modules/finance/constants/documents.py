"""Finance doc types, number sequences, docflow link types, posting-default purposes and
background-job keys (D-012/D-019/D-032). Split out of the single constants.py at the
400-line cap (STRUCTURE §8.4)."""

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

# docflow link type joining a revaluation run's adjustment entry to its auto-reversal (D-012).
FX_REVALUES_LINK = "revalues"

# Bank reconciliation (PLAN 4.9): statements register in core_documents with doc_number NULL
# (external documents, not Atlas-numbered); a clearing entry links statement->'posts'->entry.
# Imports above the sync max run as a background job (202 {job_id}, PERFORMANCE §3);
# BANK_UNMATCHED_CLEARING is the suspense posting purpose for clearing bank-only lines.
BANK_STATEMENT_DOC_TYPE = "finance.bank_statement"
BANK_CLEARING_POSTS_LINK = "posts"
BANK_UNMATCHED_CLEARING = "bank_unmatched_clearing"
BANK_IMPORT_SYNC_MAX_LINES = 1000
BANK_STATEMENT_IMPORT_JOB = "finance.bank_statement_import"


# --- Asset accounting lite (PLAN 4.10) -----------------------------------------
# Assets register at creation (doc_number NULL) and claim the gapless AST number at
# ACTIVATION (the D-012 claim-at-permanence moment); depreciation runs claim DEP at posting.
# Capitalization (activate with capitalize=True) posts Dr asset / Cr the
# ASSET_ACQUISITION_CLEARING posting default; runs above the sync max execute as a
# background job (202 {job_id}, PERFORMANCE §3).
ASSET_DOC_TYPE = "finance.asset"
ASSET_SEQUENCE_NAME = "finance.asset"
ASSET_NUMBER_PREFIX = "AST"
ASSET_NUMBER_PADDING = 5
ASSET_POSTS_LINK = "posts"
ASSET_ACQUISITION_CLEARING = "asset_acquisition_clearing"
DEPRECIATION_RUN_DOC_TYPE = "finance.depreciation_run"
DEPRECIATION_SEQUENCE_NAME = "finance.depreciation"
DEPRECIATION_NUMBER_PREFIX = "DEP"
DEPRECIATION_NUMBER_PADDING = 5
DEPRECIATION_POSTS_LINK = "posts"
DEPRECIATION_RUN_JOB = "finance.depreciation_run"
DEPRECIATION_RUN_SYNC_MAX_ASSETS = 100

# --- Procurement goods-receipt / GR-IR clearing (PLAN 6.3, D-041) -------------
# The GR/IR (goods-received / invoice-received) clearing account is a per-tenant posting default
# (a LIABILITY/clearing account). A goods receipt (6.3) posts Dr Inventory / Cr GR-IR via the
# inventory costing event's valuation-offset OVERRIDE; the matched vendor bill (6.4) posts
# Dr GR-IR / Cr AP, clearing the account. A tenant MUST map this purpose before a GR can post —
# the GR has nowhere to credit otherwise (resolved via finance/queries.gr_ir_clearing_account).
GR_IR_CLEARING = "gr_ir_clearing"

# Every known posting-default purpose: FX + the CO/bank/asset clearing accounts + GR-IR.
POSTING_PURPOSES: frozenset[str] = FX_POSTING_PURPOSES | frozenset(
    {
        CO_ALLOCATION_CLEARING,
        BANK_UNMATCHED_CLEARING,
        ASSET_ACQUISITION_CLEARING,
        GR_IR_CLEARING,
    }
)

# Background-job registry keys (PLAN 4P.5/D-032, closes #26): long-running finance operations
# execute as jobs — their POST endpoints return 202 {job_id} for /api/v1/jobs polling.
FX_REVALUATION_JOB = "finance.fx_revaluation"
AP_PAYMENT_RUN_JOB = "finance.payment_run"
