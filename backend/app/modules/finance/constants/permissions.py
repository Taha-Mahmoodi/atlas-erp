"""Finance permission keys (D-009) — one key per guarded endpoint action — registered into
the core RBAC catalog at import so tenants can only be granted keys an endpoint checks.
Split out of the single constants.py at the 400-line cap (STRUCTURE §8.4)."""

from app.core.rbac import register_permissions

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
# Asset accounting lite (PLAN 4.10): read assets/runs/register, manage+activate assets;
# running depreciation posts a journal, so it is its own action (D-009).
FINANCE_ASSET_READ = "finance.asset.read"
FINANCE_ASSET_MANAGE = "finance.asset.manage"
FINANCE_DEPRECIATION_RUN = "finance.depreciation.run"

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
    FINANCE_ASSET_READ,
    FINANCE_ASSET_MANAGE,
    FINANCE_DEPRECIATION_RUN,
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
        FINANCE_ASSET_READ: "Read assets, depreciation runs and the asset register",
        FINANCE_ASSET_MANAGE: "Create, edit and activate assets",
        FINANCE_DEPRECIATION_RUN: "Run depreciation for a fiscal period",
    },
)
